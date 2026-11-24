"""Trusted CPU studio thumbnail worker. No packages outside Blender's runtime."""
import json
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from asset_import import import_asset


def main():
    source, output, size, *options = sys.argv[sys.argv.index("--") + 1:]
    output, size = Path(output), int(size)
    started = time.perf_counter()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _, asset = import_asset(Path(source), "asset", "unit", "center", profile=options[0] if options else "static")
    if asset["missing_textures"]:
        raise ValueError(f"Missing textures: {asset['missing_textures']}")
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device, scene.cycles.samples = "CPU", 24
    scene.cycles.use_denoising, scene.cycles.seed = True, 0
    scene.render.resolution_x = scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.threads_mode, scene.render.threads = "FIXED", 4
    scene.world = bpy.data.worlds.new("Thumbnail world")
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.12, 0.15, 0.2, 1)
    background.inputs["Strength"].default_value = 0.5
    floor_z = -asset["dimensions"][2] / max(asset["dimensions"]) / 2 - 0.02
    bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, floor_z))
    floor = bpy.context.object
    floor.name = "Thumbnail floor"
    mat = bpy.data.materials.new("Neutral floor")
    mat.use_nodes = True
    mat.node_tree.nodes.get("Principled BSDF").inputs["Base Color"].default_value = (0.12, 0.15, 0.19, 1)
    floor.data.materials.append(mat)
    camera_data = bpy.data.cameras.new("Thumbnail camera")
    camera = bpy.data.objects.new("Thumbnail camera", camera_data)
    scene.collection.objects.link(camera)
    camera.location = (3, -4, 2.6)
    camera.rotation_euler = (-camera.location).to_track_quat("-Z", "Y").to_euler()
    camera_data.type, camera_data.ortho_scale = "ORTHO", 1.9
    scene.camera = camera
    for name, position, energy, color in [
        ("Key", (2, -3, 4), 500, (1, 0.9, 0.75)),
        ("Fill", (-3, -1, 2), 250, (0.7, 0.85, 1)),
        ("Rim", (1, 3, 3), 450, (1, 1, 1)),
    ]:
        data = bpy.data.lights.new(name, "AREA")
        data.energy, data.color, data.size = energy, color, 3
        light = bpy.data.objects.new(name, data)
        scene.collection.objects.link(light)
        light.location = position
        light.rotation_euler = (-Vector(position)).to_track_quat("-Z", "Y").to_euler()
    build_seconds = time.perf_counter() - started
    scene.render.filepath = str(output / "thumbnail.png")
    render_start = time.perf_counter()
    bpy.ops.render.render(write_still=True)
    report = {"blender_version": bpy.app.version_string, "engine": "CYCLES", "device": "CPU", "samples": 24,
              "build_seconds": build_seconds, "render_seconds": time.perf_counter() - render_start,
              "asset_dimensions": asset["dimensions"], "import_seconds": asset["import_seconds"]}
    (output / "render-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
