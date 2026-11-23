"""Job metadata survives process restarts; no global database connections."""
import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def contained_path(root: Path, relative: str) -> Path:
    """Resolve a child path, rejecting absolute paths and symlink escapes."""
    if Path(relative).is_absolute():
        raise ValueError("Expected a relative output path")
    root = root.resolve()
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root) or candidate == root:
        raise ValueError("Output path escapes the approved directory")
    return candidate


def atomic_json(path: Path, value: Any) -> None:
    """Replace a JSON document atomically on its destination filesystem."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(value, handle, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class JobStore:
    """SQLite-backed job history. Interrupted jobs remain explicitly unfinished."""

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL, directory TEXT NOT NULL,
                status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                error TEXT)""")

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        return db

    def create(self, job_id: str, project_id: str, directory: Path) -> None:
        now = utc_now()
        with self._connect() as db:
            db.execute("INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (job_id, project_id, str(directory), "running", now, now, None))

    def update(self, job_id: str, status: str, error: str | None = None) -> None:
        if status not in {"running", "succeeded", "failed", "cancelled"}:
            raise ValueError(f"Unknown job status: {status}")
        with self._connect() as db:
            cursor = db.execute("UPDATE jobs SET status=?, updated_at=?, error=? WHERE id=?",
                                (status, utc_now(), error, job_id))
            if cursor.rowcount != 1:
                raise ValueError(f"Unknown job: {job_id}")

    def list(self) -> list[dict]:
        with self._connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM jobs ORDER BY created_at DESC")]


def list_jobs(output_root: Path) -> list[dict]:
    """Read history without creating directories, databases or tables."""
    path = contained_path(output_root, "jobs.sqlite3")
    if not path.exists():
        return []
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=30) as db:
        db.row_factory = sqlite3.Row
        return [dict(row) for row in db.execute("SELECT * FROM jobs ORDER BY created_at DESC")]
