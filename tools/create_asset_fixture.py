"""Generate an original reusable GLB lantern, with no downloaded content.

Run inside Blender: blender -b --factory-startup --python this.py -- output.glb
This is a fixture generator, not a video-specific animation script.
"""
import json
import sys
from pathlib import Path

import bpy


def make_material(name, color, metallic=0):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    shader = material.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Metallic"].default_value = metallic
    shader.inputs["Roughness"].default_value = 0.32
    return material


def main():
    output = Path(sys.argv[sys.argv.index("--") + 1]).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    metal = make_material("Teal enamel", (0.025, 0.3, 0.35), 0.5)
    brass = make_material("Brass", (0.75, 0.38, 0.07), 0.7)
    amber = make_material("Amber core", (1, 0.45, 0.07), 0.1)
    assembly = bpy.data.objects.new("Original lantern assembly", None)
    bpy.context.scene.collection.objects.link(assembly)

    def part(name, material, location, scale=(1, 1, 1)):
        obj = bpy.context.object
        obj.name = name
        obj.location, obj.scale = location, scale
        obj.data.materials.append(material)
        obj.parent = assembly

    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.65, depth=0.22)
    part("Foot", metal, (0, 0, 0.11))
    for x, y in [(-0.43, -0.43), (-0.43, 0.43), (0.43, -0.43), (0.43, 0.43)]:
        bpy.ops.mesh.primitive_cube_add(size=1)
        part("Support", brass, (x, y, 1.05), (0.09, 0.09, 1.7))
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=1)
    part("Lamp", amber, (0, 0, 1.08), (0.36, 0.36, 0.7))
    bpy.ops.mesh.primitive_cone_add(vertices=24, radius1=0.75, radius2=0.2, depth=0.45)
    part("Canopy", metal, (0, 0, 2.1))
    bpy.ops.mesh.primitive_torus_add(major_radius=0.23, minor_radius=0.045, major_segments=24, minor_segments=8)
    part("Handle", brass, (0, 0, 2.55))
    bpy.context.object.rotation_euler.x = 1.57079632679
    # Non-origin assembly intentionally exercises aggregate pivot/scale normalization.
    assembly.location = (2, -1, 0.7)
    bpy.ops.export_scene.gltf(filepath=str(output), export_format="GLB", export_animations=False,
                              export_extras=False, export_cameras=False, export_lights=False)
    meta = {"name": "Original ATLAS lantern", "creator": "ATLAS local procedural fixture generator",
        "source_url": "urn:atlas:fixture:lantern:v1", "license_id": "LicenseRef-ATLAS-Generated",
        "license_text": "Original primitive geometry and materials generated locally for this ATLAS project. "
                        "Use and modification in local ATLAS test renders are authorized by the project brief. "
                        "No third-party assets are included. This record does not grant third-party redistribution rights.",
        "approval": "approved", "render_allowed": True, "redistribution_allowed": False,
        "attribution": "", "category": "prop", "tags": ["lantern", "original", "static"],
        "description": "Reusable eight-part static lantern with teal enamel, brass supports and amber core."}
    output.with_suffix(".provenance.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
