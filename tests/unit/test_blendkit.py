import struct

import pytest

from engine.assets.blendkit import import_blendkit
from engine.assets.models import Provenance
from engine.assets.registry import AssetRegistry


PROVIDER_ID = "c7d96fe8-1bb1-44e0-80fb-f1a301cee6ba"
SOURCE_URL = f"https://www.blendkit.com/asset-gallery-detail/{PROVIDER_ID}/"


def reviewed(**overrides):
    return Provenance(**({"name": "Local fixture", "creator": "ATLAS test generator",
                          "source_url": SOURCE_URL, "license_id": "CC0-1.0",
                          "license_text": "CC0 fixture evidence", "approval": "approved",
                          "render_allowed": True} | overrides))


@pytest.mark.parametrize(("overrides", "plan", "message"), [
    ({"license_id": "LicenseRef-Blendkit-Royalty-Free"}, "free", "CC0"),
    ({}, "full", "free-plan"),
    ({"approval": "unreviewed"}, "free", "approved"),
    ({"redistribution_allowed": True}, "free", "redistribution"),
    ({"source_url": SOURCE_URL.replace("www.blendkit.com", "blendkit.com.invalid")}, "free", "asset page"),
    ({"source_url": SOURCE_URL.replace(PROVIDER_ID, "f040ff82-b152-46ea-a800-af760db847d2")}, "free", "asset page"),
])
def test_requires_reviewed_free_cc0_private_import(tmp_path, overrides, plan, message):
    with pytest.raises(ValueError, match=message):
        import_blendkit(tmp_path / "absent.blend", "blendkit-fixture", reviewed(**overrides),
                        AssetRegistry(tmp_path / "library"), provider_asset_id=PROVIDER_ID,
                        plan=plan, objects=("Mesh",))


def test_requires_blendkit_namespace_for_local_id(tmp_path):
    with pytest.raises(ValueError, match="blendkit- prefix"):
        import_blendkit(tmp_path / "absent.blend", "polyhaven-other-provider", reviewed(),
                        AssetRegistry(tmp_path / "library"), provider_asset_id=PROVIDER_ID,
                        plan="free", objects=("Mesh",))


@pytest.mark.parametrize(("contents", "message"), [
    (b"\x28\xb5\x2f\xfd" + bytes(64), "uncompressed"),
    (b"BLENDER17-01v0502" + struct.pack("<4siQqq", b"LI\0\0", 0, 0, 1, 1) + b"x", "linked librar"),
    (b"BLENDER-v402" + struct.pack("<4siQii", b"TX\0\0", 1, 0, 0, 1) + b"x", "text blocks"),
    (b"BLENDER17-01v0502" + struct.pack("<4siQqq", b"DATA", 0, 0, 1_000_000, 1), "block length"),
])
def test_preflight_rejects_native_input_without_starting_blender(tmp_path, contents, message):
    source = tmp_path / "input.blend"
    source.write_bytes(contents)
    registry = AssetRegistry(tmp_path / "library")
    with pytest.raises(ValueError, match=message):
        import_blendkit(source, "blendkit-fixture", reviewed(), registry, provider_asset_id=PROVIDER_ID,
                        plan="free", objects=("Mesh",), blender=tmp_path / "missing.exe")
    assert registry.search() == []
    assert source.read_bytes() == contents
