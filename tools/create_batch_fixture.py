"""Create an original mixed input collection for batch acceptance tests.

Run with Blender: --python tools/create_batch_fixture.py -- OUTPUT_DIRECTORY
No downloaded content; generated inputs deliberately include invalid/unreviewed cases.
"""
import json
import shutil
import sys
from pathlib import Path

import bpy


def material(name, color):
    value = bpy.data.materials.new(name)
    value.use_nodes = True
    shader = value.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Roughness"].default_value = 0.38
    return value


def metadata(name, approval="approved"):
    return {"name": name, "creator": "ATLAS original batch fixture generator",
        "source_url": "urn:atlas:fixture:batch:v1", "license_id": "LicenseRef-ATLAS-Generated",
        "license_text": "Original primitive geometry generated locally for ATLAS testing and render demonstrations. No third-party content.",
        "approval": approval, "render_allowed": approval == "approved", "redistribution_allowed": False,
        "category": "prop", "tags": ["batch-fixture", "original"]}


def main():
    root = Path(sys.argv[sys.argv.index("--") + 1]).resolve()
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise ValueError("Fixture destination must be empty; use a fresh directory")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    orange = material("Orange enamel", (0.9, 0.22, 0.04))
    gray = material("Dark base", (0.07, 0.1, 0.14))
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.7, depth=0.2, location=(0, 0, 0.1))
    bpy.context.object.data.materials.append(gray)
    bpy.ops.mesh.primitive_cone_add(vertices=24, radius1=0.5, radius2=0.15, depth=1.6, location=(0, 0, 1))
    bpy.context.object.data.materials.append(orange)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=20, ring_count=12, radius=0.24, location=(0, 0, 1.9))
    bpy.context.object.data.materials.append(orange)
    bpy.ops.export_scene.gltf(filepath=str(root / "beacon.glb"), export_format="GLB", export_animations=False)
    (root / "beacon.provenance.json").write_text(json.dumps(metadata("Original beacon"), indent=2), encoding="utf-8")

    bpy.ops.wm.read_factory_settings(use_empty=True)
    wood = material("Blue crate", (0.04, 0.24, 0.42))
    trim = material("Golden trim", (0.75, 0.43, 0.09))
    bpy.ops.mesh.primitive_cube_add(size=1.6, location=(0, 0, 0.8))
    bpy.context.object.data.materials.append(wood)
    for z in (0.15, 1.45):
        for y in (-0.82, 0.82):
            bpy.ops.mesh.primitive_cube_add(size=1, location=(0, y, z))
            bpy.context.object.scale = (1.7, 0.08, 0.18)
            bpy.context.object.data.materials.append(trim)
    bpy.ops.export_scene.gltf(filepath=str(root / "crate.glb"), export_format="GLB", export_animations=False)
    (root / "crate.provenance.json").write_text(json.dumps(metadata("Original crate"), indent=2), encoding="utf-8")
    shutil.copyfile(root / "beacon.glb", root / "beacon-copy.glb")
    (root / "beacon-copy.provenance.json").write_text(json.dumps(metadata("Original beacon duplicate"), indent=2), encoding="utf-8")
    shutil.copyfile(root / "crate.glb", root / "unreviewed.glb")
    (root / "unreviewed.provenance.json").write_text(json.dumps(metadata("Unreviewed demonstration", "unreviewed"), indent=2), encoding="utf-8")
    (root / "corrupt.glb").write_bytes(b"Deliberately invalid GLB fixture")
    (root / "corrupt.provenance.json").write_text(json.dumps(metadata("Invalid container demonstration"), indent=2), encoding="utf-8")
    (root / "unsupported.obj").write_text("# deliberately unsupported input format\n", encoding="utf-8")


if __name__ == "__main__":
    main()
