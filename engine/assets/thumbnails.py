"""Render and verify local asset thumbnails without altering inspection status."""
import json
import logging
import shutil
import time
import uuid
from pathlib import Path

from engine.assets.registry import AssetRegistry, file_hash
from engine.quality.images import verify_png
from engine.rendering.runtime import find_tool, run_logged
from engine.storage.jobs import atomic_json, contained_path

LOG = logging.getLogger("atlas")


def create_thumbnail(registry: AssetRegistry, asset_id: str, version: int, *, size: int = 256,
                     blender: Path | None = None, timeout: int = 180) -> dict:
    """Return verified thumbnail evidence; failed attempts keep diagnostic logs."""
    if type(size) is not int or size not in {128, 256, 512}:
        raise ValueError("Thumbnail size must be 128, 256 or 512")
    registry.get(asset_id, version)
    workspace = contained_path(registry.root, f"thumbnails/{uuid.uuid4().hex}")
    workspace.mkdir(parents=True)
    source = workspace / "source.glb"
    started = time.perf_counter()
    try:
        entry = registry.resolve(asset_id, version)
        shutil.copyfile(entry["path"], source)
        if file_hash(source) != entry["sha256"]:
            raise ValueError("Asset source hash changed during thumbnail snapshot")
        worker = Path(__file__).resolve().parents[1] / "adapters" / "blender" / "thumbnail.py"
        elapsed = run_logged([str(find_tool("blender", blender)), "--background", "--factory-startup",
            "--disable-autoexec", "--threads", "4", "--python-exit-code", "1", "--python", str(worker),
            "--", str(source), str(workspace), str(size), entry["container"].get("profile", "static")],
            workspace / "blender.log", timeout)
        report = json.loads((workspace / "render-report.json").read_text(encoding="utf-8"))
        image_path = workspace / "thumbnail.png"
        report.update(verify_png(image_path, size))
        report.update(profile="atlas-thumbnail-1", source_sha256=entry["sha256"], image_sha256=file_hash(image_path),
                      image_file=image_path.relative_to(registry.root).as_posix(), process_seconds=elapsed,
                      total_seconds=time.perf_counter() - started,
                      log=(workspace / "blender.log").relative_to(registry.root).as_posix())
        atomic_json(workspace / "report.json", report)
        registry.set_thumbnail(asset_id, version, "ready", report)
        LOG.info("thumbnail_created", extra={"asset_id": asset_id, "version": version})
        return report
    except BaseException as exc:
        report = {"error": f"{type(exc).__name__}: {exc}", "total_seconds": time.perf_counter() - started,
                  "log": (workspace / "blender.log").relative_to(registry.root).as_posix()}
        for operation in (lambda: registry.set_thumbnail(asset_id, version, "failed", report),
                          lambda: atomic_json(workspace / "report.json", report)):
            try:
                operation()
            except Exception as persistence_error:
                LOG.error("thumbnail_failure_persistence_error", extra={"error": str(persistence_error)})
        raise
    finally:
        try:
            source.unlink(missing_ok=True)
        except OSError as exc:
            LOG.error("thumbnail_snapshot_cleanup_failed", extra={"error": str(exc)})
