"""Versioned local provenance registry with deduplicated immutable GLB blobs."""
import hashlib
import json
import os
import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path

from pydantic import TypeAdapter

from engine.assets.glb import MAX_GLB_BYTES, inspect_glb
from engine.assets.models import InspectionProof, Provenance, ThumbnailProof
from engine.core.models import Identifier
from engine.storage.jobs import contained_path, utc_now

ID = TypeAdapter(Identifier)


def file_hash(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


class AssetRegistry:
    """Database schema 2. Records pin provenance independently of shared bytes."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.path = contained_path(self.root, "assets.sqlite3")
        self.root.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in {0, 1, 2}:
                raise ValueError(f"Unsupported asset registry schema {version}; expected 2")
            if version == 0:
                if db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone():
                    raise ValueError("Refusing to initialize an unversioned nonempty asset database")
                db.execute("""CREATE TABLE asset_versions (
                    id TEXT NOT NULL, version INTEGER NOT NULL, sha256 TEXT NOT NULL,
                    provenance TEXT NOT NULL, container TEXT NOT NULL, created_at TEXT NOT NULL,
                    PRIMARY KEY(id,version))""")
                db.execute("""CREATE TABLE inspections (
                    id TEXT NOT NULL, version INTEGER NOT NULL, status TEXT NOT NULL,
                    report TEXT NOT NULL, updated_at TEXT NOT NULL,
                    PRIMARY KEY(id,version), FOREIGN KEY(id,version) REFERENCES asset_versions(id,version))""")
                db.execute("CREATE INDEX asset_hash ON asset_versions(sha256)")
            if version < 2:
                db.execute("""CREATE TABLE thumbnails (
                    id TEXT NOT NULL, version INTEGER NOT NULL, status TEXT NOT NULL,
                    report TEXT NOT NULL, updated_at TEXT NOT NULL,
                    PRIMARY KEY(id,version), FOREIGN KEY(id,version) REFERENCES asset_versions(id,version))""")
                db.execute("PRAGMA user_version=2")

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def register(self, source: Path, asset_id: str, provenance: Provenance) -> dict:
        """Snapshot a local GLB; identical latest registration is idempotent."""
        ID.validate_python(asset_id)
        provenance = Provenance.model_validate(provenance.model_dump())
        if source.suffix.lower() != ".glb" or not source.is_file():
            raise ValueError("Asset source must be an existing local .glb file")
        if source.stat().st_size > MAX_GLB_BYTES:
            raise ValueError("GLB exceeds 256 MiB")
        blob_dir = contained_path(self.root, "blobs")
        blob_dir.mkdir(exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=blob_dir, suffix=".incoming", delete=False) as destination:
                temporary = Path(destination.name)
                count = 0
                with source.open("rb") as handle:
                    while chunk := handle.read(1024 * 1024):
                        count += len(chunk)
                        if count > MAX_GLB_BYTES:
                            raise ValueError("GLB exceeds 256 MiB")
                        destination.write(chunk)
                destination.flush()
                os.fsync(destination.fileno())
            container = inspect_glb(temporary)
            digest = file_hash(temporary)
            blob = contained_path(self.root, f"blobs/{digest}.glb")
            metadata = json.dumps(provenance.model_dump(mode="json"), sort_keys=True)
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                if blob.exists():
                    if file_hash(blob) != digest:
                        raise ValueError("Existing asset blob hash mismatch; restore the library before registration")
                else:
                    os.replace(temporary, blob)
                latest = db.execute("SELECT * FROM asset_versions WHERE id=? ORDER BY version DESC LIMIT 1", (asset_id,)).fetchone()
                if latest and latest["sha256"] == digest and latest["provenance"] == metadata:
                    version = latest["version"]
                else:
                    version = latest["version"] + 1 if latest else 1
                    if version > 9223372036854775807:
                        raise ValueError("Asset version exceeds SQLite integer range")
                    db.execute("INSERT INTO asset_versions VALUES (?,?,?,?,?,?)",
                               (asset_id, version, digest, metadata, json.dumps(container), utc_now()))
            return self.get(asset_id, version)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def get(self, asset_id: str, version: int) -> dict:
        ID.validate_python(asset_id)
        if type(version) is not int or not 1 <= version <= 9223372036854775807:
            raise ValueError("Asset version must be a positive signed 64-bit integer")
        with self._connect() as db:
            row = db.execute("SELECT * FROM asset_versions WHERE id=? AND version=?", (asset_id, version)).fetchone()
            if row is None:
                raise ValueError(f"Asset {asset_id} version {version} not found")
            inspection = db.execute("SELECT * FROM inspections WHERE id=? AND version=?", (asset_id, version)).fetchone()
            thumbnail = db.execute("SELECT * FROM thumbnails WHERE id=? AND version=?", (asset_id, version)).fetchone()
        result = dict(row)
        result["provenance"] = json.loads(result["provenance"])
        result["container"] = json.loads(result["container"])
        result["inspection"] = ({"status": inspection["status"], "report": json.loads(inspection["report"]),
                                 "updated_at": inspection["updated_at"]} if inspection else {"status": "pending"})
        result["thumbnail"] = ({"status": thumbnail["status"], "report": json.loads(thumbnail["report"]),
                                "updated_at": thumbnail["updated_at"]} if thumbnail else {"status": "pending"})
        return result

    def search(self, *, query: str = "", tag: str | None = None, category: str | None = None,
               license_id: str | None = None) -> list[dict]:
        """Literal case-insensitive text search, latest versions, sorted by ID."""
        with self._connect() as db:
            latest = db.execute("SELECT id, MAX(version) AS version FROM asset_versions GROUP BY id ORDER BY id").fetchall()
        results = []
        for row in latest:
            entry = self.get(row["id"], row["version"])
            meta = entry["provenance"]
            text = " ".join([entry["id"], meta["name"], meta["description"], *meta["tags"]]).casefold()
            if (query.casefold() in text and (tag is None or tag.casefold() in meta["tags"])
                    and (category is None or meta["category"] == category)
                    and (license_id is None or meta["license_id"] == license_id)):
                results.append(entry)
        return results

    def set_inspection(self, asset_id: str, version: int, status: str, report: dict) -> None:
        if status not in {"ready", "failed"}:
            raise ValueError("Inspection status must be ready or failed")
        entry = self.get(asset_id, version)
        if status == "ready":
            self._check_inspection(entry, report)
        with self._connect() as db:
            db.execute("INSERT OR REPLACE INTO inspections VALUES (?,?,?,?,?)",
                       (asset_id, version, status, json.dumps(report, allow_nan=False), utc_now()))

    def resolve(self, asset_id: str, version: int, *, require_inspection: bool = True) -> dict:
        entry = self.get(asset_id, version)
        Provenance.model_validate(entry["provenance"]).require_render_rights()
        digest = entry["sha256"]
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("Invalid registry content hash")
        path = contained_path(self.root, f"blobs/{digest}.glb")
        if not path.is_file() or file_hash(path) != digest:
            raise ValueError(f"Asset {asset_id} version {version} is missing or has a content hash mismatch")
        inspect_glb(path)
        if require_inspection and entry["inspection"]["status"] != "ready":
            raise ValueError(f"Asset {asset_id} version {version} requires successful Blender inspection")
        if require_inspection:
            self._check_inspection(entry, entry["inspection"]["report"])
        return entry | {"path": path}

    @staticmethod
    def _check_inspection(entry: dict, report: dict) -> None:
        proof = InspectionProof.model_validate(report)
        if proof.source_sha256 != entry["sha256"]:
            raise ValueError("Inspection content hash does not match the registered asset version")

    def set_thumbnail(self, asset_id: str, version: int, status: str, report: dict) -> None:
        if status not in {"ready", "failed"}:
            raise ValueError("Thumbnail status must be ready or failed")
        entry = self.get(asset_id, version)
        if status == "ready":
            entry = self.resolve(asset_id, version)
            self._check_thumbnail(entry, report)
        with self._connect() as db:
            db.execute("INSERT OR REPLACE INTO thumbnails VALUES (?,?,?,?,?)",
                       (asset_id, version, status, json.dumps(report, allow_nan=False), utc_now()))

    def _check_thumbnail(self, entry: dict, report: dict) -> Path:
        proof = ThumbnailProof.model_validate(report)
        if proof.source_sha256 != entry["sha256"]:
            raise ValueError("Thumbnail source hash does not match the registered asset")
        path = contained_path(self.root, proof.image_file)
        if not path.is_file() or file_hash(path) != proof.image_sha256:
            raise ValueError("Thumbnail is missing or has an image hash mismatch")
        from engine.quality.images import verify_png
        actual = verify_png(path, proof.width)
        for field in ("codec", "width", "height", "pixel_min", "pixel_max", "spatial_range"):
            if actual[field] != getattr(proof, field):
                raise ValueError(f"Thumbnail decoded {field} does not match its proof")
        return path

    def resolve_thumbnail(self, asset_id: str, version: int) -> dict:
        entry = self.resolve(asset_id, version)
        if entry["thumbnail"]["status"] != "ready":
            raise ValueError("Asset requires a successful thumbnail attempt")
        report = entry["thumbnail"]["report"]
        return report | {"path": self._check_thumbnail(entry, report)}
