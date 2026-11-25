"""Blender-generated fixtures exercise native conversion without a provider download."""
import json
import os
from pathlib import Path

import pytest

from engine.assets.blendkit import import_blendkit
from engine.assets.models import Provenance
from engine.assets.registry import AssetRegistry, file_hash
from engine.core.models import Project
from engine.rendering.pipeline import render_project
from engine.rendering.runtime import capture, find_tool


pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(os.environ.get("ATLAS_INTEGRATION") != "1", reason="set ATLAS_INTEGRATION=1")]
PROVIDER_ID = "c7d96fe8-1bb1-44e0-80fb-f1a301cee6ba"


def run_blender(*args):
    return capture([str(find_tool("blender")), "--background", "--factory-startup", "--offline-mode",
                    "--disable-autoexec", "--python-exit-code", "1", *map(str, args)], timeout=120)


@pytest.fixture(scope="module")
def native_sources(tmp_path_factory):
    directory = tmp_path_factory.mktemp("native-sources")
    generator = directory / "generate.py"
    generator.write_text('''import bpy, struct, sys, zlib
from pathlib import Path

destination = Path(sys.argv[-1])
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.preferences.filepaths.save_version = 0
parts = bpy.data.collections.new("Test Collection")
bpy.context.scene.collection.children.link(parts)
nested = bpy.data.collections.new("Test Nested")
parts.children.link(nested)
root = bpy.data.objects.new("Test Root", None)
parts.objects.link(root)
bpy.ops.mesh.primitive_cube_add(size=2)
mesh = bpy.context.object
mesh.name = "Test Mesh"
mesh.parent = root
mesh.location = (0, 0, 1)
for collection in list(mesh.users_collection):
    collection.objects.unlink(mesh)
nested.objects.link(mesh)
mesh.data.uv_layers.new(name="SecondaryUV")
mesh.modifiers.new("Safe Triangles", "TRIANGULATE")
bpy.ops.mesh.primitive_uv_sphere_add()
bpy.context.object.name = "Outside Selection"

def chunk(name, body):
    return struct.pack(">I", len(body)) + name + body + struct.pack(">I", zlib.crc32(name + body))

texture = destination / "checker.png"
texture.write_bytes(b"\\x89PNG\\r\\n\\x1a\\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0))
    + chunk(b"IDAT", zlib.compress(bytes([0, 255, 0, 0, 0, 255, 0, 0, 0, 0, 255, 255, 255, 0])))
    + chunk(b"IEND", b""))
image = bpy.data.images.load(str(texture))
material = bpy.data.materials.new("Test Textured Material")
material.use_nodes = True
tree = material.node_tree
node = tree.nodes.new("ShaderNodeTexImage")
node.image = image
tree.links.new(node.outputs["Color"], tree.nodes.get("Principled BSDF").inputs["Base Color"])
mesh.data.materials.append(material)
plain = bpy.data.materials.new("Test Plain Material")
plain.use_nodes = True
plain.node_tree.nodes.get("Principled BSDF").inputs["Base Color"].default_value = (0.15, 0.4, 0.07, 1)
mesh.data.materials.append(plain)
mesh.data.polygons[1].material_index = 1

def save(name):
    bpy.ops.wm.save_as_mainfile(filepath=str(destination / name), compress=False)

save("external.blend")
image.pack()
save("packed.blend")
floating = bpy.data.images.new("Test Float", width=2, height=2, float_buffer=True)
floating.pixels[:] = [0.4, 0.4, 0.4, 1] * 4
floating.filepath_raw = str(destination / "roughness.exr")
floating.file_format = "OPEN_EXR"
floating.save()
packed_exr = bpy.data.images.load(floating.filepath_raw)
packed_exr.colorspace_settings.name = "Non-Color"
packed_exr.pack()
roughness = tree.nodes.new("ShaderNodeTexImage")
roughness.image = packed_exr
tree.links.new(roughness.outputs["Color"], tree.nodes.get("Principled BSDF").inputs["Roughness"])
save("exr.blend")
tree.nodes.remove(roughness)
root["asset_data"] = {"assetBaseId": "c7d96fe8-1bb1-44e0-80fb-f1a301cee6ba", "isFree": True, "license": "royalty_free"}
save("license-mismatch.blend")
del root["asset_data"]
mesh.driver_add("location", 0).driver.expression = "0.25"
save("driver.blend")
mesh.driver_remove("location", 0)
text = bpy.data.texts.new("never-execute.py")
text.write("raise RuntimeError('This source script must never execute')")
text.use_module = True
save("script.blend")
bpy.ops.wm.read_factory_settings(use_empty=True)
with bpy.data.libraries.load(str(destination / "packed.blend"), link=True) as (available, requested):
    requested.collections = ["Test Collection"]
bpy.context.scene.collection.children.link(requested.collections[0])
save("linked.blend")
''', encoding="utf-8")
    run_blender("--python", generator, "--", directory)
    return directory


def import_fixture(registry, source, choices):
    evidence = Provenance(name="Native profile fixture", creator="ATLAS test generator",
                          source_url=f"https://www.blendkit.com/asset-gallery-detail/{PROVIDER_ID}/",
                          license_id="CC0-1.0", license_text="Offline fixture provenance for testing only.",
                          approval="approved", render_allowed=True)
    return import_blendkit(source, "blendkit-native-fixture", evidence, registry,
                           provider_asset_id=PROVIDER_ID, plan="free", **choices)


@pytest.mark.parametrize("choices", [{"objects": ("Test Mesh", "Test Root")},
                                     {"collections": ("Test Collection",)}])
def test_native_import_preserves_packed_textures_materials_and_source(native_sources, tmp_path, choices):
    registry = AssetRegistry(tmp_path / "library")
    source = native_sources / "packed.blend"
    original_hash = file_hash(source)
    receipt = import_fixture(registry, source, choices)
    assert file_hash(source) == original_hash == file_hash(registry.root / receipt["source"]["file"])
    assert receipt["source"]["sha256"] == original_hash
    assert receipt["conversion"]["object_count"] == 2
    assert receipt["conversion"]["source_triangle_count"] == 12
    entry = registry.resolve("blendkit-native-fixture", 1)
    inspection = entry["inspection"]["report"]
    assert inspection["mesh_count"] == 1
    assert inspection["polygon_count"] == 12
    assert inspection["materials"] == ["Test Plain Material", "Test Textured Material"]
    assert inspection["texture_count"] == 1
    assert inspection["textures"][0]["size"] == [2, 2]
    assert inspection["textures"][0]["packed"]
    assert inspection["dimensions"] == pytest.approx([2, 2, 2])
    assert not entry["provenance"]["redistribution_allowed"]
    assert json.loads((registry.root / receipt["receipt_file"]).read_text(encoding="utf-8")) == receipt
    retry = import_fixture(registry, source, choices)
    assert retry["asset"]["version"] == 1
    assert retry["asset"]["sha256"] == entry["sha256"]

    if "collections" in choices:
        project = Project.model_validate({"schema_version": "1.1", "id": "native-reopen",
            "render": {"width": 64, "height": 64, "frames": 2, "fps": 2, "samples": 2}, "scene": {
                "entities": [{"id": "native", "asset": {"id": "blendkit-native-fixture", "version": 1}}],
                "camera": {"location": [6, -8, 4], "target": [0, 0, 1]}}})
        video = render_project(project, tmp_path / "outputs", asset_library=registry.root)
        check = tmp_path / "reopen.py"
        check.write_text('''import bpy
meshes = [item for item in bpy.data.objects["native"].children_recursive if item.type == "MESH"]
assert len(meshes) == 1
assert len(meshes[0].data.polygons) == 12
assert len(meshes[0].data.uv_layers) == 2
assert len(meshes[0].material_slots) == 2
images = [node.image for slot in meshes[0].material_slots for node in slot.material.node_tree.nodes if node.type == "TEX_IMAGE"]
assert len(images) == 1 and images[0].packed_file and tuple(images[0].size) == (2, 2)
assert not bpy.data.libraries
print("NATIVE_DERIVATIVE_REOPENED")
''', encoding="utf-8")
        stdout = run_blender(video.parent / "scene.blend", "--python", check)
        assert "NATIVE_DERIVATIVE_REOPENED" in stdout


@pytest.mark.parametrize(("filename", "choices", "error"), [
    ("external.blend", {"collections": ("Test Collection",)}, "external paths"),
    ("driver.blend", {"collections": ("Test Collection",)}, "drivers"),
    ("script.blend", {"collections": ("Test Collection",)}, "text blocks"),
    ("linked.blend", {"collections": ("Test Collection",)}, "linked libraries"),
    ("license-mismatch.blend", {"collections": ("Test Collection",)}, "metadata does not match"),
    ("packed.blend", {"objects": ("Test Mesh",)}, "requires its parent"),
    ("packed.blend", {"objects": ("Missing Mesh",)}, "were not found"),
])
def test_native_import_rejects_unsafe_or_incomplete_data(native_sources, tmp_path, filename, choices, error):
    registry = AssetRegistry(tmp_path / "library")
    with pytest.raises(ValueError, match=error):
        import_fixture(registry, native_sources / filename, choices)
    assert registry.search() == []


def test_bounded_source_exr_expands_to_embedded_glb_texture(native_sources, tmp_path):
    registry = AssetRegistry(tmp_path / "library")
    receipt = import_fixture(registry, native_sources / "exr.blend", {"collections": ("Test Collection",)})
    assert receipt["conversion"]["texture_count"] == receipt["conversion"]["derivative_texture_count"] == 2
    assert receipt["conversion"]["material_texture_channels"]["Test Textured Material"] == [
        "baseColorTexture", "metallicRoughnessTexture"]
    inspection = registry.resolve("blendkit-native-fixture", 1)["inspection"]["report"]
    assert inspection["texture_count"] == 2
    assert not inspection["missing_textures"]
    assert all(texture["size"] == [2, 2] and texture["packed"] for texture in inspection["textures"])
