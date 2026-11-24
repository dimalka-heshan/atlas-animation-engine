"""Immutable local PCM audio versions with explicit usage and consent provenance."""
import json
import os
import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from pydantic import StrictBool, TypeAdapter

from engine.assets.models import Provenance
from engine.assets.registry import file_hash
from engine.audio.validation import verify_wav
from engine.core.models import Identifier
from engine.storage.jobs import contained_path, utc_now

ID = TypeAdapter(Identifier)
MAX_AUDIO_BYTES = 64 * 1024 * 1024


class AudioProvenance(Provenance):
    voice_origin: Literal["synthetic", "recording"]
    voice_owner: str = ""
    consent_to_use: StrictBool = False

    def require_audio_rights(self):
        self.require_render_rights()
        if self.voice_origin == "recording" and (not self.voice_owner.strip() or not self.consent_to_use):
            raise ValueError("Recordings require voice owner and explicit consent_to_use")


class AudioLibrary:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.database = contained_path(self.root, "audio.sqlite3")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in {0, 1}:
                raise ValueError("Unsupported audio library schema")
            if version == 0:
                if db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone():
                    raise ValueError("Refusing an unversioned nonempty audio database")
                db.execute("""CREATE TABLE clips (id TEXT, version INTEGER, sha256 TEXT, provenance TEXT,
                    metadata TEXT, created_at TEXT, PRIMARY KEY(id,version))""")
                db.execute("CREATE INDEX clip_hash ON clips(sha256)")
                db.execute("PRAGMA user_version=1")

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.database, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def register(self, source: Path, clip_id: str, provenance: AudioProvenance) -> dict:
        ID.validate_python(clip_id)
        provenance = AudioProvenance.model_validate(provenance.model_dump())
        provenance.require_audio_rights()
        if source.suffix.lower() != ".wav" or not source.is_file() or source.stat().st_size > MAX_AUDIO_BYTES:
            raise ValueError("Audio source must be a local WAV no larger than 64 MiB")
        blob_dir = contained_path(self.root, "blobs")
        blob_dir.mkdir(exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=blob_dir, suffix=".wav", delete=False) as handle:
                temporary = Path(handle.name)
                count = 0
                with source.open("rb") as reader:
                    while chunk := reader.read(1024 * 1024):
                        count += len(chunk)
                        if count > MAX_AUDIO_BYTES:
                            raise ValueError("Audio exceeds 64 MiB")
                        handle.write(chunk)
                handle.flush(); os.fsync(handle.fileno())
            metadata = verify_wav(temporary)
            digest = file_hash(temporary)
            blob = contained_path(self.root, f"blobs/{digest}.wav")
            meta_json = json.dumps(provenance.model_dump(mode="json"), sort_keys=True)
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                if blob.exists():
                    if file_hash(blob) != digest:
                        raise ValueError("Existing audio blob hash mismatch")
                else:
                    os.replace(temporary, blob)
                latest = db.execute("SELECT * FROM clips WHERE id=? ORDER BY version DESC LIMIT 1", (clip_id,)).fetchone()
                if latest and latest["sha256"] == digest and latest["provenance"] == meta_json:
                    version = latest["version"]
                else:
                    version = latest["version"] + 1 if latest else 1
                    db.execute("INSERT INTO clips VALUES (?,?,?,?,?,?)", (clip_id, version, digest, meta_json,
                        json.dumps(metadata, allow_nan=False), utc_now()))
            return self.get(clip_id, version)
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)

    def get(self, clip_id: str, version: int) -> dict:
        ID.validate_python(clip_id)
        if type(version) is not int or not 1 <= version <= 9223372036854775807:
            raise ValueError("Audio version must be a positive signed 64-bit integer")
        with self._connect() as db:
            row = db.execute("SELECT * FROM clips WHERE id=? AND version=?", (clip_id, version)).fetchone()
        if row is None:
            raise ValueError(f"Audio {clip_id}@{version} not found")
        return dict(row) | {"provenance": json.loads(row["provenance"]), "metadata": json.loads(row["metadata"])}

    def list(self) -> list[dict]:
        with self._connect() as db:
            rows = db.execute("SELECT id, MAX(version) AS version FROM clips GROUP BY id ORDER BY id").fetchall()
        return [self.get(row["id"], row["version"]) for row in rows]

    def resolve(self, clip_id: str, version: int) -> dict:
        entry = self.get(clip_id, version)
        AudioProvenance.model_validate(entry["provenance"]).require_audio_rights()
        digest = entry["sha256"]
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("Invalid audio hash")
        path = contained_path(self.root, f"blobs/{digest}.wav")
        if not path.is_file() or file_hash(path) != digest:
            raise ValueError("Audio source missing or hash mismatch")
        return entry | {"path": path, "metadata": verify_wav(path)}
