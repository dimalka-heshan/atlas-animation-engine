import os
import struct
import zlib
from pathlib import Path

import pytest

from engine.assets.inspection import inspect_asset
from engine.assets.models import Provenance
from engine.assets.registry import AssetRegistry
from engine.assets.thumbnails import create_thumbnail
from engine.quality.images import verify_png

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(os.environ.get("ATLAS_INTEGRATION") != "1", reason="set ATLAS_INTEGRATION=1")]


def registered(tmp_path):
    fixture = Path(__file__).resolve().parents[2] / "assets" / "fixtures" / "lantern.glb"
    registry = AssetRegistry(tmp_path / "library")
    meta = Provenance.model_validate_json(fixture.with_suffix(".provenance.json").read_text())
    registry.register(fixture, "lantern", meta)
    inspect_asset(registry, "lantern", 1)
    return registry


def test_real_thumbnail_has_pixels_and_persisted_provenance(tmp_path):
    registry = registered(tmp_path)
    result = create_thumbnail(registry, "lantern", 1, size=128)
    assert result["width"] == result["height"] == 128
    assert result["codec"] == "png"
    assert result["pixel_max"] - result["pixel_min"] > 8
    assert (registry.root / result["image_file"]).stat().st_size > 1000
    entry = AssetRegistry(registry.root).get("lantern", 1)
    assert entry["thumbnail"]["status"] == "ready"
    assert entry["thumbnail"]["report"]["source_sha256"] == entry["sha256"]
    resolved = registry.resolve_thumbnail("lantern", 1)
    assert resolved["path"].is_file()
    assert not list((registry.root / "thumbnails").glob("*/source.glb"))
    resolved["path"].write_bytes(b"tampered")
    with pytest.raises(ValueError, match="hash|PNG"):
        registry.resolve_thumbnail("lantern", 1)


def test_failed_thumbnail_is_explicit_and_preserves_inspection(tmp_path):
    registry = registered(tmp_path)
    with pytest.raises(FileNotFoundError):
        create_thumbnail(registry, "lantern", 1, size=128, blender=tmp_path / "missing.exe")
    entry = registry.get("lantern", 1)
    assert entry["inspection"]["status"] == "ready"
    assert entry["thumbnail"]["status"] == "failed"
    assert "missing.exe" in entry["thumbnail"]["report"]["error"]
    assert not list((registry.root / "thumbnails").glob("*/source.glb"))


def test_thumbnail_requires_prior_inspection(tmp_path):
    fixture = Path(__file__).resolve().parents[2] / "assets" / "fixtures" / "lantern.glb"
    registry = AssetRegistry(tmp_path / "library")
    registry.register(fixture, "lantern", Provenance.model_validate_json(fixture.with_suffix(".provenance.json").read_text()))
    with pytest.raises(ValueError, match="inspection"):
        create_thumbnail(registry, "lantern", 1, size=128)
    assert registry.get("lantern", 1)["thumbnail"]["status"] == "failed"


def test_uniform_colored_png_is_rejected(tmp_path):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    raw = (b"\0" + b"\xff\0\0" * 128) * 128
    payload = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 128, 128, 8, 2, 0, 0, 0))
               + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
    path = tmp_path / "uniform.png"
    path.write_bytes(payload)
    with pytest.raises(ValueError, match="uniform"):
        verify_png(path, 128)


@pytest.mark.parametrize("damage", ["missing_end", "bad_crc"])
def test_decodable_but_damaged_png_is_rejected(tmp_path, damage):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    raw = b"".join(b"\0" + bytes([row, 255 - row, 90]) * 128 for row in range(128))
    payload = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 128, 128, 8, 2, 0, 0, 0))
               + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
    if damage == "missing_end":
        payload = payload[:-12]
    else:
        payload = payload[:-13] + bytes([payload[-13] ^ 1]) + payload[-12:]
    path = tmp_path / "damaged.png"
    path.write_bytes(payload)
    with pytest.raises(ValueError, match="PNG"):
        verify_png(path, 128)
