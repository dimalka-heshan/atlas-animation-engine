"""Deterministic discovery and explicitly selected, hash-bound batch registration."""
import hashlib
import logging
import os
import re
import sqlite3
import stat
import subprocess
import time
import uuid
from contextlib import contextmanager
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Annotated, Literal, Self

from pydantic import Field, StrictBool, field_validator, model_validator

from engine.assets.glb import MAX_GLB_BYTES
from engine.assets.inspection import inspect_asset
from engine.assets.models import Provenance
from engine.assets.registry import AssetRegistry
from engine.core.models import Identifier, Model
from engine.storage.jobs import atomic_json, contained_path, utc_now

LOG = logging.getLogger("atlas")
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class BatchEntry(Model):
    path: Annotated[str, Field(min_length=1, max_length=2000)]
    id: Identifier
    kind: Literal["candidate", "unsupported", "blocked", "error"]
    selected: StrictBool = False
    sha256: Digest | None = None
    provenance_sha256: Digest | None = None
    name: str = ""
    approval: str = ""
    license_id: str = ""
    note: str = ""

    @field_validator("path")
    @classmethod
    def portable_relative_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if ("\\" in value or ":" in value or path.is_absolute() or PureWindowsPath(value).drive
                or any(part in {"", ".", ".."} for part in value.split("/"))):
            raise ValueError("Batch paths must be portable relative paths without traversal")
        return value


class BatchPlan(Model):
    schema_version: Literal["1.0"] = "1.0"
    source_root: str
    entries: list[BatchEntry] = Field(default_factory=list, max_length=10000)

    @model_validator(mode="after")
    def unique_entries(self) -> Self:
        paths = [entry.path for entry in self.entries]
        ids = [entry.id for entry in self.entries if entry.selected]
        if len(paths) != len(set(paths)) or len(ids) != len(set(ids)):
            raise ValueError("Batch paths and selected IDs must be unique")
        return self


def _linked(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def source_path(root: Path, relative: str) -> Path:
    """Reject child links/junctions, including links that stay inside the root."""
    BatchEntry.portable_relative_path(relative)
    current = root.resolve()
    for part in PurePosixPath(relative).parts:
        current /= part
        if _linked(current):
            raise ValueError(f"Linked source paths are not permitted: {relative}")
    return contained_path(root, relative)


def _suggest_id(relative: str) -> str:
    slug = re.sub(r"[^a-z0-9_-]+", "-", PurePosixPath(relative).stem.casefold()).strip("-")[:35] or "file"
    return f"asset-{slug}-{hashlib.sha256(relative.encode('utf-8')).hexdigest()[:16]}"


@contextmanager
def _regular_reader(path: Path):
    """Nonblocking open plus descriptor check prevents a replaced FIFO from hanging."""
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, flags)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("Source must be a regular file")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            yield handle
    finally:
        os.close(descriptor)


def _source_hash(path: Path) -> str:
    digest, count = hashlib.sha256(), 0
    with _regular_reader(path) as reader:
        while chunk := reader.read(1024 * 1024):
            count += len(chunk)
            if count > MAX_GLB_BYTES:
                raise ValueError("GLB exceeds 256 MiB")
            digest.update(chunk)
    return digest.hexdigest()


def _sidecar_bytes(root: Path, relative: str) -> bytes:
    sidecar = str(PurePosixPath(relative).with_suffix(".provenance.json"))
    path = source_path(root, sidecar)
    with _regular_reader(path) as handle:
        value = handle.read(500001)
    if len(value) > 500000:
        raise ValueError("Provenance JSON exceeds 500 KB")
    return value


def scan_directory(root: Path, *, recursive: bool = True) -> BatchPlan:
    """Inventory regular files without following links or inferring approval."""
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"Source root must be a directory: {root}")
    entries = []
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            if directory != root:
                source_path(root, directory.relative_to(root).as_posix())
            with os.scandir(directory) as handle:
                children = sorted(handle, key=lambda item: item.name)
        except (OSError, ValueError) as exc:
            if directory == root:
                raise
            relative = directory.relative_to(root).as_posix()
            entries.append(BatchEntry(path=relative, id=_suggest_id(relative), kind="error", note=str(exc)))
            continue
        for child in children:
            path = Path(child.path)
            relative = path.relative_to(root).as_posix()
            entry = BatchEntry(path=relative, id=_suggest_id(relative), kind="unsupported")
            try:
                if _linked(path):
                    entry.kind, entry.note = "blocked", "Symlinks and directory junctions are not followed"
                elif child.is_dir(follow_symlinks=False):
                    if recursive:
                        pending.append(path)
                    continue
                elif not child.is_file(follow_symlinks=False):
                    entry.kind, entry.note = "blocked", "Only regular files are eligible"
                elif path.name.lower().endswith(".provenance.json"):
                    continue
                elif path.suffix.lower() != ".glb":
                    entry.note = "Unsupported format; only .glb is currently accepted"
                else:
                    entry.kind = "candidate"
                    if path.stat().st_size > MAX_GLB_BYTES:
                        raise ValueError("GLB exceeds 256 MiB")
                    entry.sha256 = _source_hash(source_path(root, relative))
                    try:
                        raw = _sidecar_bytes(root, relative)
                        entry.provenance_sha256 = hashlib.sha256(raw).hexdigest()
                        meta = Provenance.model_validate_json(raw.decode("utf-8-sig"))
                        entry.name, entry.approval, entry.license_id = meta.name, meta.approval, meta.license_id
                        meta.require_render_rights()
                        entry.note = "Declared render rights present; selection still required"
                    except (OSError, ValueError) as exc:
                        entry.note = f"Provenance requires attention: {exc}"
            except (OSError, ValueError) as exc:
                entry.note = str(exc)
            entries.append(entry)
            if len(entries) > 10000:
                raise ValueError("Scan exceeds 10000 files; choose a smaller source root")
    return BatchPlan(source_root=str(root), entries=sorted(entries, key=lambda entry: entry.path))


def _snapshot(source: Path, target: Path) -> str:
    digest, count = hashlib.sha256(), 0
    with _regular_reader(source) as reader, target.open("xb") as writer:
        while chunk := reader.read(1024 * 1024):
            count += len(chunk)
            if count > MAX_GLB_BYTES:
                raise ValueError("GLB exceeds 256 MiB")
            writer.write(chunk)
            digest.update(chunk)
    return digest.hexdigest()


def apply_batch(plan: BatchPlan, source_root: Path, library: Path, *, inspect: bool = False,
                thumbnails: bool = False, size: int = 256, blender: Path | None = None) -> dict:
    """Apply selected entries, persisting each outcome and continuing on file errors."""
    plan = BatchPlan.model_validate(plan.model_dump(mode="json"))
    source_root, library = source_root.resolve(), library.resolve()
    if source_root != Path(plan.source_root).resolve() or not source_root.is_dir():
        raise ValueError("Explicit source root must match the reviewed plan root")
    if library.is_relative_to(source_root) or source_root.is_relative_to(library):
        raise ValueError("Library and source root must not overlap or be inside each other")
    if not any(entry.selected for entry in plan.entries):
        raise ValueError("No assets selected; review the plan and set selected=true explicitly")
    if size not in {128, 256, 512} or type(size) is not int:
        raise ValueError("Thumbnail size must be 128, 256 or 512")
    registry = AssetRegistry(library)
    batch_id = uuid.uuid4().hex
    workspace = contained_path(library, f"batches/{batch_id}")
    workspace.mkdir(parents=True)
    atomic_json(workspace / "plan.json", plan.model_dump(mode="json"))
    report = {"id": batch_id, "status": "running", "started_at": utc_now(), "source_root": str(source_root),
              "report_file": f"batches/{batch_id}/report.json",
              "entries": [{"path": entry.path, "id": entry.id, "status": "pending" if entry.selected else "skipped"}
                          for entry in plan.entries],
              "summary": {"selected": sum(entry.selected for entry in plan.entries), "succeeded": 0, "failed": 0, "skipped": 0}}
    started = time.perf_counter()
    def checkpoint():
        states = [entry["status"] for entry in report["entries"]]
        report["summary"].update(succeeded=sum(state in {"registered", "ready", "thumbnail_ready"} for state in states),
                                 failed=states.count("failed"), skipped=states.count("skipped"))
        atomic_json(workspace / "report.json", report)
    checkpoint()
    try:
        for index, entry in enumerate(plan.entries):
            result = report["entries"][index]
            item_start = time.perf_counter()
            if not entry.selected:
                continue
            else:
                result["status"] = "running"
                checkpoint()
                snapshot = workspace / f"source-{index}.glb"
                try:
                    if entry.kind != "candidate" or PurePosixPath(entry.path).suffix.lower() != ".glb":
                        raise ValueError("Only regular GLB candidates may be selected")
                    if not entry.sha256 or not entry.provenance_sha256:
                        raise ValueError("Source or provenance hash is missing; fix the sidecar and rescan")
                    raw = _sidecar_bytes(source_root, entry.path)
                    if hashlib.sha256(raw).hexdigest() != entry.provenance_sha256:
                        raise ValueError("Provenance changed after review; rescan before registration")
                    meta = Provenance.model_validate_json(raw.decode("utf-8-sig"))
                    meta.require_render_rights()
                    source = source_path(source_root, entry.path)
                    if not source.is_file():
                        raise ValueError("Selected source is not a regular file")
                    if _snapshot(source, snapshot) != entry.sha256:
                        raise ValueError("Source content changed after review; rescan before registration")
                    registered = registry.register(snapshot, entry.id, meta)
                    result.update(version=registered["version"], sha256=registered["sha256"], stage="registered")
                    completed_status = "registered"
                    if inspect or thumbnails:
                        inspect_asset(registry, entry.id, registered["version"], blender=blender)
                        result["stage"] = completed_status = "ready"
                    if thumbnails:
                        from engine.assets.thumbnails import create_thumbnail
                        result["thumbnail"] = create_thumbnail(registry, entry.id, registered["version"], size=size, blender=blender)
                        completed_status = "thumbnail_ready"
                    result["status"] = completed_status
                except (OSError, ValueError, RuntimeError, sqlite3.Error, subprocess.SubprocessError) as exc:
                    result.update(status="failed", error=f"{type(exc).__name__}: {exc}")
                    LOG.error("batch_item_failed", extra={"asset_id": entry.id, "error": str(exc)})
                finally:
                    try:
                        snapshot.unlink(missing_ok=True)
                    except OSError as exc:
                        result["cleanup_error"] = str(exc)
                        LOG.error("batch_snapshot_cleanup_failed", extra={"error": str(exc)})
            result["seconds"] = time.perf_counter() - item_start
            checkpoint()
        failed, succeeded = report["summary"]["failed"], report["summary"]["succeeded"]
        report["status"] = "partial" if failed and succeeded else "failed" if failed else "succeeded"
    except KeyboardInterrupt:
        report["status"] = "cancelled"
        for result in report["entries"]:
            if result["status"] == "running":
                result.update(status="cancelled", error="Interrupted; completed registration is retained")
        raise
    except Exception as exc:
        report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        report["finished_at"] = utc_now()
        report["seconds"] = time.perf_counter() - started
        checkpoint()
    return report
