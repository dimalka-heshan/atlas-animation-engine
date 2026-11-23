import sqlite3

import pytest

from engine.storage.jobs import JobStore, list_jobs


def test_listing_preserves_database_bytes(tmp_path):
    store = JobStore(tmp_path / "jobs.sqlite3")
    store.create("one", "project", tmp_path / "one")
    before = (tmp_path / "jobs.sqlite3").read_bytes()
    assert list_jobs(tmp_path)[0]["id"] == "one"
    assert (tmp_path / "jobs.sqlite3").read_bytes() == before


def test_listing_does_not_initialize_unknown_database(tmp_path):
    path = tmp_path / "jobs.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE unrelated (id TEXT)")
    before = path.read_bytes()
    with pytest.raises(sqlite3.OperationalError, match="no such table"):
        list_jobs(tmp_path)
    assert path.read_bytes() == before


def test_database_symlink_escape_is_rejected(tmp_path):
    root = tmp_path / "approved"
    root.mkdir()
    outside = tmp_path / "outside.sqlite3"
    outside.write_bytes(b"untouched")
    try:
        (root / "jobs.sqlite3").symlink_to(outside)
    except OSError:
        pytest.skip("OS user lacks file-symlink privilege")
    with pytest.raises(ValueError, match="escapes"):
        list_jobs(root)
    assert outside.read_bytes() == b"untouched"
