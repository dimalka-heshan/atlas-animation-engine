"""Trusted Blender entrypoint; accepts only host-validated resolved JSON.

Run via ATLAS, never import this module in the orchestration interpreter.
No host packages (including Pydantic) are needed inside Blender.
"""
import json
import math
import statistics
import sys
import time
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from asset_import import import_asset
from facial import build_talking_head, apply_performance


def material(spec, name):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    shader = mat.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*spec["color"], 1)
    shader.inputs["Metallic"].default_value = spec["metallic"]
    shader.inputs["Roughness"].default_value = spec["roughness"]
    return mat


def apply_transform(obj, spec):
    if spec.get("location") is not None:
        obj.location = spec["location"]
    if spec.get("rotation") is not None:
        obj.rotation_euler = [math.radians(v) for v in spec["rotation"]]
    if spec.get("scale") is not None:
        obj.scale = spec["scale"]


def animate(obj, spec):
    keys = spec["keyframes"]
    if not keys:
        return
    # Explicit base keys prevent a delayed first key from moving the object early.
    channels = {channel for key in keys for channel in ("location", "rotation", "scale")
                if key.get(channel) is not None}
    paths = {"location": "location", "rotation": "rotation_euler", "scale": "scale"}
    for channel in channels:
        obj.keyframe_insert(data_path=paths[channel], frame=1)
    for key in keys:
        apply_transform(obj, key)
        for channel in channels:
            if key.get(channel) is not None:
                obj.keyframe_insert(data_path=paths[channel], frame=key["frame"])
    action = obj.animation_data.action
    if hasattr(action, "fcurves"):
        curves = list(action.fcurves)
    else:
        curves = [curve for layer in action.layers for strip in layer.strips
                  for bag in strip.channelbags for curve in bag.fcurves]
    for curve in curves:
        for key in curve.keyframe_points:
            key.interpolation = spec["interpolation"]


def create_entity(spec):
    builders = {
        "cube": lambda: bpy.ops.mesh.primitive_cube_add(size=2),
        "uv_sphere": lambda: bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=1),
        "ico_sphere": lambda: bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=1),
        "cylinder": lambda: bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=1, depth=2),
        "cone": lambda: bpy.ops.mesh.primitive_cone_add(vertices=32, radius1=1, radius2=0, depth=2),
        "torus": lambda: bpy.ops.mesh.primitive_torus_add(major_radius=1, minor_radius=0.25,
                                                       major_segments=48, minor_segments=12),
        "plane": lambda: bpy.ops.mesh.primitive_plane_add(size=2),
    }
    builders[spec["primitive"]]()
    obj = bpy.context.object
    obj.name = spec["id"]
    apply_transform(obj, spec)
    obj.data.materials.append(material(spec["material"], f"{obj.name}_material"))
    if spec["bevel"] and spec["primitive"] in {"cube", "cylinder"}:
        modifier = obj.modifiers.new("Edge highlights", "BEVEL")
        modifier.width = spec["bevel"]
        modifier.segments = 3
    if spec["smooth"] and spec["primitive"] in {"uv_sphere", "ico_sphere", "torus"}:
        for polygon in obj.data.polygons:
            polygon.use_smooth = True
    animate(obj, spec)
    return obj


def aim(obj, point):
    direction = Vector(point) - obj.location
    if direction.length < 1e-8:
        raise ValueError(f"{obj.name} is positioned at its aim target")
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def media_image(directory, entry, channel):
    source = next(item["source_file"] for item in entry["files"] if item["channel"] == channel)
    path = (directory / source).resolve()
    if not path.is_relative_to(directory.resolve()):
        raise ValueError("Environment media escapes job directory")
    image = bpy.data.images.load(str(path), check_existing=True)
    if not all(image.size) or not image.has_data or max(image.size) > 4096:
        raise ValueError(f"Invalid or oversized environment image: {channel}")
    image.pack()
    return image


def apply_ground_media(material, directory, entry, repeats):
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    shader = nodes.get("Principled BSDF")
    coords = nodes.new("ShaderNodeTexCoord")
    scale = nodes.new("ShaderNodeVectorMath")
    scale.operation = "SCALE"
    scale.inputs["Scale"].default_value = repeats
    links.new(coords.outputs["Object"], scale.inputs[0])
    textures = {}
    for channel in sorted(item["channel"] for item in entry["files"]):
        texture = nodes.new("ShaderNodeTexImage")
        texture.label = channel
        texture.image = media_image(directory, entry, channel)
        links.new(scale.outputs["Vector"], texture.inputs["Vector"])
        if channel not in {"Diffuse", "Emission"}:
            texture.image.colorspace_settings.name = "Non-Color"
        textures[channel] = texture.outputs["Alpha"] if channel == "Opacity" and texture.image.channels == 4 else texture.outputs["Color"]
    diffuse = textures["Diffuse"]
    if "AO" in textures:
        multiply = nodes.new("ShaderNodeMixRGB")
        multiply.blend_type = "MULTIPLY"
        multiply.inputs[0].default_value = .35
        links.new(diffuse, multiply.inputs[1])
        links.new(textures["AO"], multiply.inputs[2])
        diffuse = multiply.outputs[0]
    links.new(diffuse, shader.inputs["Base Color"])
    for channel, destination in (("Rough", "Roughness"), ("Metal", "Metallic"),
                                 ("Opacity", "Alpha"), ("Emission", "Emission Color")):
        if channel in textures:
            links.new(textures[channel], shader.inputs[destination])
    if "Emission" in textures:
        shader.inputs["Emission Strength"].default_value = 1
    normal = nodes.new("ShaderNodeNormalMap")
    links.new(textures["nor_gl"], normal.inputs["Color"])
    normal_output = normal.outputs["Normal"]
    height = textures.get("Displacement", textures.get("Height"))
    if height is not None:
        bump = nodes.new("ShaderNodeBump")
        bump.inputs["Distance"].default_value = .015
        links.new(height, bump.inputs["Height"])
        links.new(normal_output, bump.inputs["Normal"])
        normal_output = bump.outputs["Normal"]
    links.new(normal_output, shader.inputs["Normal"])


def build(project, directory):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    settings, spec = project["render"], project["scene"]
    quality = project.get("quality") or {}
    scene.frame_start, scene.frame_end = 1, settings["frames"]
    scene.render.fps, scene.render.fps_base = settings["fps"], 1.0
    scene.render.resolution_x = settings["width"]
    scene.render.resolution_y = settings["height"]
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.threads_mode, scene.render.threads = "FIXED", settings["threads"]
    if settings["engine"] == "cycles":
        scene.render.engine = "CYCLES"
        scene.cycles.device = "CPU"
        scene.cycles.samples = settings["samples"]
        scene.cycles.seed = project["seed"]
        scene.cycles.use_denoising = quality.get("denoise", True)
    else:
        # Blender 4.2 used NEXT; Blender 5 uses BLENDER_EEVEE again.
        errors = []
        for engine in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):
            try:
                scene.render.engine = engine
                break
            except TypeError as exc:
                errors.append(str(exc))
        else:
            raise RuntimeError(f"Eevee unavailable: {errors}; select cycles for CPU rendering")
        if hasattr(scene, "eevee"):
            if hasattr(scene.eevee, "taa_render_samples"):
                scene.eevee.taa_render_samples = settings["samples"]
    if "AgX" in [x.identifier for x in scene.view_settings.bl_rna.properties["view_transform"].enum_items]:
        scene.view_settings.view_transform = "AgX"
    if quality:
        scene.view_settings.exposure = quality["exposure"]
        if quality.get("look") is not None:
            scene.view_settings.look = quality["look"]
        if quality.get("motion_blur"):
            scene.render.use_motion_blur = True
    world = bpy.data.worlds.new("ATLAS_world")
    scene.world = world
    world.use_nodes = True
    environment = spec["environment"]
    background = world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (*environment["background"], 1)
    background.inputs["Strength"].default_value = environment["strength"]
    media_path = directory / "environment-map.json"
    media = json.loads(media_path.read_text(encoding="utf-8")) if media_path.is_file() else {}
    if "hdri" in media:
        sky = world.node_tree.nodes.new("ShaderNodeTexEnvironment")
        sky.image = media_image(directory, media["hdri"], "hdri")
        world.node_tree.links.new(sky.outputs["Color"], background.inputs["Color"])
    asset_map = json.loads((directory / "asset-map.json").read_text(encoding="utf-8"))
    entities, imported_assets, rig_equipment = {}, [], []
    for item in spec["entities"]:
        if "asset" in item:
            reference = item["asset"]
            entry = asset_map[f"{reference['id']}@{reference['version']}"]
            source = (directory / entry["source_file"]).resolve()
            if not source.is_relative_to(directory.resolve()):
                raise ValueError("Asset snapshot escapes job directory")
            obj, report = import_asset(source, item["id"], item["normalize"], item["pivot"],
                profile=entry["container"].get("profile", "static"), clips=item.get("clips", []), fps=settings["fps"])
            if report["missing_textures"]:
                raise ValueError(f"Missing asset textures: {report['missing_textures']}")
            apply_transform(obj, item)
            animate(obj, item)
            imported_assets.append({"entity": item["id"], "asset": reference, **report})
            if item.get("equipment"):
                rig = next(child for child in obj.children_recursive if child.type == "ARMATURE")
                rig_equipment.append((rig, report["humanoid_mapping"], item["equipment"]))
        elif "character" in item:
            obj = build_talking_head(item)
            apply_transform(obj, item)
            animate(obj, item)
        else:
            obj = create_entity(item)
        entities[item["id"]] = obj
    for rig, mapping, equipment in rig_equipment:
        for role, identifier in equipment.items():
            prop = entities[identifier]
            prop.parent = rig
            prop.parent_type = "BONE"
            prop.parent_bone = mapping[role]
    audio_events = {event["id"]: event for event in project.get("audio", [])}
    for performance in project.get("performances", []):
        event = audio_events[performance["audio_event_id"]]
        apply_performance(entities[performance["actor_id"]],
                          performance | {"start_seconds": event["start_seconds"]}, settings["fps"])
    if environment["ground"]:
        bpy.ops.mesh.primitive_plane_add(size=environment["ground_size"])
        ground = bpy.context.object
        ground.name = "ATLAS_ground"
        ground.data.materials.append(material(environment["ground_material"], "Ground"))
        if "material" in media:
            apply_ground_media(ground.data.materials[0], directory, media["material"],
                               environment["texture_repeats_per_meter"])
    for light in spec["lights"]:
        data = bpy.data.lights.new(light["id"], light["kind"])
        data.energy, data.color = light["energy"], light["color"]
        if light.get("temperature_kelvin") is not None:
            data.use_temperature = True
            data.temperature = light["temperature_kelvin"]
        if light.get("cast_shadows") is not None:
            data.use_shadow = light["cast_shadows"]
        if light["kind"] == "AREA":
            data.shape, data.size = "DISK", light["size"]
        elif light["kind"] == "POINT":
            data.shadow_soft_size = light["size"]
        obj = bpy.data.objects.new(light["id"], data)
        scene.collection.objects.link(obj)
        obj.location = light["location"]
        if light["kind"] != "POINT":
            aim(obj, light["target"])
    spec_camera = spec["camera"]
    data = bpy.data.cameras.new("ATLAS_camera")
    camera = bpy.data.objects.new("ATLAS_camera", data)
    scene.collection.objects.link(camera)
    camera.location = spec_camera["location"]
    camera.data.lens = spec_camera["lens"]
    camera.data.clip_end = 10000
    scene.camera = camera
    if spec_camera["target_entity"]:
        target = entities[spec_camera["target_entity"]]
    else:
        target = bpy.data.objects.new("ATLAS_focus", None)
        target.location = spec_camera["target"]
        scene.collection.objects.link(target)
    constraint = camera.constraints.new("TRACK_TO")
    constraint.target = target
    constraint.track_axis, constraint.up_axis = "TRACK_NEGATIVE_Z", "UP_Y"
    data.dof.use_dof = spec_camera["depth_of_field"]
    data.dof.focus_object = target
    data.dof.aperture_fstop = spec_camera["fstop"]
    animate(camera, spec_camera)
    if project.get("audio"):
        mix_path = directory / "audio-mix.wav"
        strip = scene.sequence_editor_create().strips.new_sound("ATLAS verified audio", str(mix_path), 1, 1)
        strip.sound.filepath = "//audio-mix.wav"
        # Keep 3D still rendering independent of the editor; retain audio for scene playback.
        scene.render.use_sequencer = False
    scene.frame_set(1)
    scene.render.filepath = str(directory / "frames" / "000001.png")
    bpy.ops.wm.save_as_mainfile(filepath=str(directory / "scene.blend"))
    return scene, entities, imported_assets


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    project_path, directory = Path(args[0]), Path(args[1])
    project = json.loads(project_path.read_text(encoding="utf-8"))
    started = time.perf_counter()
    scene, entities, imported_assets = build(project, directory)
    build_time = time.perf_counter() - started
    frame_seconds, warnings = [], []
    for frame in range(1, project["render"]["frames"] + 1):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        visible = []
        for identifier, obj in entities.items():
            coordinate = world_to_camera_view(scene, scene.camera, obj.matrix_world.translation)
            if 0 <= coordinate.x <= 1 and 0 <= coordinate.y <= 1 and coordinate.z > 0:
                visible.append(identifier)
        if not visible:
            warnings.append(f"frame {frame}: no entity centers inside camera frame")
        start = time.perf_counter()
        scene.render.filepath = str(directory / "frames" / f"{frame:06d}.png")
        bpy.ops.render.render(write_still=True)
        frame_seconds.append(time.perf_counter() - start)
        print(json.dumps({"event": "frame_rendered", "frame": frame, "seconds": frame_seconds[-1]}), flush=True)
    report = {"version": bpy.app.version_string, "engine": scene.render.engine,
              "build_seconds": build_time, "render_seconds": sum(frame_seconds),
              "mean_frame_seconds": statistics.mean(frame_seconds), "frame_seconds": frame_seconds,
              "entity_count": len(entities), "warnings": warnings, "imported_assets": imported_assets}
    (directory / "blender-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
