import json
import sqlite3

import pytest

from engine.assets.registry import AssetRegistry
from engine.quality.images import validate_png_probe


def test_v1_registry_migrates_without_losing_records(tmp_path):
    root = tmp_path / "library"
    root.mkdir()
    with sqlite3.connect(root / "assets.sqlite3") as db:
        db.executescript("""CREATE TABLE asset_versions (id TEXT, version INTEGER, sha256 TEXT,
            provenance TEXT, container TEXT, created_at TEXT, PRIMARY KEY(id,version));
            CREATE TABLE inspections (id TEXT, version INTEGER, status TEXT, report TEXT,
            updated_at TEXT, PRIMARY KEY(id,version)); PRAGMA user_version=1;""")
        db.execute("INSERT INTO asset_versions VALUES (?,?,?,?,?,?)", ("old", 7, "a" * 64,
            json.dumps({"name": "Preserved"}), "{}", "original-date"))
        db.execute("INSERT INTO inspections VALUES (?,?,?,?,?)", ("old", 7, "failed", '{"error":"old failure"}', "original-date"))
    registry = AssetRegistry(root)
    old = registry.get("old", 7)
    assert old["provenance"]["name"] == "Preserved"
    assert old["inspection"]["report"]["error"] == "old failure"
    assert old["thumbnail"]["status"] == "pending"
    with sqlite3.connect(registry.path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2
    assert AssetRegistry(root).get("old", 7) == old


def test_png_probe_contract():
    data = {"streams": [{"codec_name": "png", "width": 256, "height": 256}]}
    assert validate_png_probe(data, 256) == {"codec": "png", "width": 256, "height": 256}


@pytest.mark.parametrize("streams", [[], [{"codec_name": "mjpeg", "width": 256, "height": 256}],
    [{"codec_name": "png", "width": 128, "height": 256}],
    [{"codec_name": "png", "width": 256, "height": 128}], [{"codec_name": "png"}]])
def test_invalid_png_probe_rejected(streams):
    with pytest.raises(ValueError):
        validate_png_probe({"streams": streams}, 256)


def test_ready_thumbnail_cannot_bypass_inspection(tmp_path):
    import struct
    from engine.assets.registry import file_hash
    from test_assets import make_glb, provenance
    source = tmp_path / "prop.glb"
    make_glb(source)
    registry = AssetRegistry(tmp_path / "library")
    entry = registry.register(source, "prop", provenance())
    image = registry.root / "forged.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 128, 128))
    proof = dict(source_sha256=entry["sha256"], image_sha256=file_hash(image), image_file=image.name,
                 profile="atlas-thumbnail-1", codec="png", width=128, height=128,
                 pixel_min=0, pixel_max=255, spatial_range=255)
    with pytest.raises(ValueError, match="inspection"):
        registry.set_thumbnail("prop", 1, "ready", proof)
    assert registry.get("prop", 1)["thumbnail"]["status"] == "pending"
