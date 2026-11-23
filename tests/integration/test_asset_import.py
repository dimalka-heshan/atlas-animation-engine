"""Actual GLB inspection, hierarchy normalization, import reuse and failures."""
import json
import os
import struct
import zlib
from pathlib import Path

import pytest

from engine.assets.inspection import inspect_asset
from engine.assets.models import Provenance
from engine.assets.registry import AssetRegistry
from engine.core.models import Project
from engine.rendering.pipeline import render_project
from engine.rendering.runtime import capture, find_tool

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(os.environ.get("ATLAS_INTEGRATION") != "1", reason="set ATLAS_INTEGRATION=1")]


@pytest.fixture
def registered_fixture(tmp_path):
    source = tmp_path / "original.glb"
    generator = Path(__file__).resolve().parents[2] / "tools" / "create_asset_fixture.py"
    capture([str(find_tool("blender")), "--background", "--factory-startup", "--disable-autoexec",
             "--python-exit-code", "1", "--python", str(generator), "--", str(source)], timeout=120)
    meta = Provenance.model_validate_json(source.with_suffix(".provenance.json").read_text())
    registry = AssetRegistry(tmp_path / "library")
    entry = registry.register(source, "lantern", meta)
    return registry, entry


def test_inspect_and_reuse_imported_asset(registered_fixture, tmp_path):
    registry, entry = registered_fixture
    report = inspect_asset(registry, "lantern", 1)
    assert report["mesh_count"] >= 4
    assert report["polygon_count"] > 20
    assert report["dimensions"][2] > report["dimensions"][0] > 0
    assert report["material_count"] >= 2
    assert report["missing_textures"] == []
    assert registry.get("lantern", 1)["inspection"]["status"] == "ready"
    for variant in range(2):
        project = Project.model_validate({"schema_version": "1.1", "id": f"reuse-{variant}",
            "render": {"width": 64, "height": 64, "frames": 2, "fps": 2, "samples": 2}, "scene": {
                "entities": [{"id": "hero", "asset": {"id": "lantern", "version": 1},
                    "normalize": "unit", "pivot": "base", "location": [0, 0, 0], "scale": [3, 3, 3],
                    "keyframes": [{"frame": 1, "rotation": [0, 0, 0]}, {"frame": 2, "rotation": [0, 0, 90]}]},
                    {"id": "other", "asset": {"id": "lantern", "version": 1}, "location": [5, 0, 0]}],
                "camera": {"location": [7 + variant, -10, 6], "target": [0, 0, 1.5]}}})
        video = render_project(project, tmp_path / "renders", asset_library=registry.root)
        manifest = json.loads((video.parent / "manifest.json").read_text())
        assert manifest["status"] == "succeeded"
        assert len(manifest["assets"]) == 1
        assert manifest["assets"][0]["sha256"] == entry["sha256"]
        assert manifest["assets"][0]["version"] == 1
        assert (video.parent / manifest["assets"][0]["source_file"]).is_file()
        assert (video.parent / "attributions.txt").is_file()
        inspector = tmp_path / "check_import.py"
        inspector.write_text("""import bpy
from mathutils import Vector
s=bpy.context.scene
s.frame_set(1)
hero=bpy.data.objects['hero']
children=list(hero.children_recursive)
points=[obj.matrix_world @ Vector(corner) for obj in children if obj.type=='MESH' for corner in obj.bound_box]
assert points
assert abs(min(p.z for p in points)) < 0.001
assert abs(max(p.z for p in points)-3) < 0.001
s.frame_set(2)
assert abs(hero.rotation_euler.z-1.57079632679) < 0.001
assert bpy.data.objects['other'].children_recursive
print('IMPORTED_OK')
""")
        result = capture([str(find_tool("blender")), "--background", "--disable-autoexec",
                          str(video.parent / "scene.blend"), "--python-exit-code", "1", "--python", str(inspector)], timeout=120)
        assert "IMPORTED_OK" in result


def test_failed_import_is_recorded(registered_fixture, tmp_path):
    registry, _ = registered_fixture
    with pytest.raises(FileNotFoundError):
        inspect_asset(registry, "lantern", 1, blender=tmp_path / "missing-blender.exe")
    entry = registry.get("lantern", 1)
    assert entry["inspection"]["status"] == "failed"
    assert "missing-blender" in entry["inspection"]["report"]["error"]
    with pytest.raises(ValueError, match="inspection"):
        registry.resolve("lantern", 1)


def test_rotated_nonbox_mesh_has_exact_bounds_and_base_pivot(tmp_path):
    generator = tmp_path / "triangle.py"
    source = tmp_path / "triangle.glb"
    generator.write_text("""import bpy, math, sys
bpy.ops.wm.read_factory_settings(use_empty=True)
mesh=bpy.data.meshes.new('triangle')
mesh.from_pydata([(0,0,0),(1,0,0),(0,0,1)],[],[(0,1,2)])
obj=bpy.data.objects.new('triangle',mesh)
bpy.context.scene.collection.objects.link(obj)
obj.rotation_euler.y=3*math.pi/4
bpy.ops.export_scene.gltf(filepath=sys.argv[-1],export_format='GLB',export_animations=False)
""")
    capture([str(find_tool("blender")), "--background", "--factory-startup", "--disable-autoexec",
             "--python-exit-code", "1", "--python", str(generator), "--", str(source)], timeout=120)
    registry = AssetRegistry(tmp_path / "library")
    meta = Provenance(name="Original triangle", creator="Test generator", source_url="urn:atlas:test:triangle",
        license_id="LicenseRef-ATLAS-Generated", license_text="Original local test geometry; local rendering permitted.",
        approval="approved", render_allowed=True)
    registry.register(source, "triangle", meta)
    report = inspect_asset(registry, "triangle", 1)
    assert report["dimensions"][0] == pytest.approx(2 ** 0.5, abs=0.0001)
    assert report["dimensions"][2] == pytest.approx(0.5 ** 0.5, abs=0.0001)
    inspector = tmp_path / "check_triangle.py"
    importer_dir = Path(__file__).resolve().parents[2] / "engine" / "adapters" / "blender"
    inspector.write_text("""import bpy, sys
sys.path.insert(0,sys.argv[-2])
from asset_import import import_asset
bpy.ops.wm.read_factory_settings(use_empty=True)
root,report=import_asset(sys.argv[-1],'hero','unit','base')
points=[obj.matrix_world @ v.co for obj in root.children_recursive if obj.type=='MESH' for v in obj.data.vertices]
assert abs(min(p.z for p in points)) < 0.0001
assert abs(max(p.x for p in points)-min(p.x for p in points)-1) < 0.0001
print('EXACT_BOUNDS_OK')
""")
    result = capture([str(find_tool("blender")), "--background", "--factory-startup", "--disable-autoexec",
                      "--python-exit-code", "1", "--python", str(inspector), "--", str(importer_dir), str(source)], timeout=120)
    assert "EXACT_BOUNDS_OK" in result


def embed_texture(source, target, corrupt=False):
    """Add a hand-built 2x1 RGB PNG to a trusted fixture's BIN chunk."""
    data = source.read_bytes()
    length = struct.unpack_from("<I", data, 12)[0]
    doc = json.loads(data[20:20 + length])
    binary = data[28 + length:][:doc["buffers"][0]["byteLength"]]
    binary += b"\0" * (-len(binary) % 4)
    def chunk(kind, payload):
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff)
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 1, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(b"\0\xff\0\0\0\xff\0")) + chunk(b"IEND", b""))
    if corrupt:
        png = b"this is not a PNG"
    views = doc.setdefault("bufferViews", [])
    view_index = len(views)
    views.append({"buffer": 0, "byteOffset": len(binary), "byteLength": len(png)})
    binary += png
    doc["buffers"][0]["byteLength"] = len(binary)
    image_index = len(doc.setdefault("images", []))
    doc["images"].append({"name": "Fixture texture", "bufferView": view_index, "mimeType": "image/png"})
    texture_index = len(doc.setdefault("textures", []))
    doc["textures"].append({"source": image_index})
    doc["materials"][0].setdefault("pbrMetallicRoughness", {})["baseColorTexture"] = {"index": texture_index}
    payload = json.dumps(doc).encode()
    payload += b" " * (-len(payload) % 4)
    binary += b"\0" * (-len(binary) % 4)
    chunks = struct.pack("<II", len(payload), 0x4E4F534A) + payload + struct.pack("<II", len(binary), 0x004E4942) + binary
    target.write_bytes(struct.pack("<4sII", b"glTF", 2, len(chunks) + 12) + chunks)


@pytest.mark.parametrize("corrupt", [False, True])
def test_embedded_texture_validation(registered_fixture, tmp_path, corrupt):
    registry, entry = registered_fixture
    textured = tmp_path / "textured.glb"
    source = registry.root / "blobs" / (entry["sha256"] + ".glb")
    embed_texture(source, textured, corrupt)
    registry.register(textured, "textured", Provenance.model_validate(entry["provenance"]))
    if corrupt:
        with pytest.raises((ValueError, RuntimeError)):
            inspect_asset(registry, "textured", 1)
        assert registry.get("textured", 1)["inspection"]["status"] == "failed"
    else:
        report = inspect_asset(registry, "textured", 1)
        assert report["texture_count"] == 1
        assert report["textures"][0]["size"] == [2, 1]
        assert report["textures"][0]["packed"] is True
        assert report["missing_textures"] == []
