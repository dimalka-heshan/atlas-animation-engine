"""Trusted bpy-only static GLB importer, shared by inspection and rendering."""
import math
import time

import bpy
from mathutils import Vector


def import_asset(path, identifier, normalize="none", pivot="origin", *, profile="static", clips=(), fps=None):
    started = time.perf_counter()
    before = set(bpy.data.objects)
    scene = bpy.context.scene
    previous_fps = scene.render.fps
    if profile == "rigged":
        scene.render.fps = 30
    try:
        result = bpy.ops.import_scene.gltf(filepath=str(path), import_pack_images=True,
                                         import_scene_extras=False, import_scene_as_collection=False)
    finally:
        scene.render.fps = previous_fps
    if "FINISHED" not in result:
        raise ValueError(f"GLB importer did not finish: {result}")
    objects = sorted(set(bpy.data.objects) - before, key=lambda obj: obj.name)
    meshes = [obj for obj in objects if obj.type == "MESH"]
    allowed = {"MESH", "EMPTY"} | ({"ARMATURE"} if profile == "rigged" else set())
    if not meshes or any(obj.type not in allowed for obj in objects):
        raise ValueError("GLB object types exceed the selected import profile")
    if profile == "static" and any(obj.animation_data or (obj.type == "MESH" and obj.data.shape_keys) for obj in objects):
        raise ValueError("Imported animation or morph targets are unsupported")
    rig_report = {}
    if profile == "rigged":
        from skeleton import inspect_skeleton, play_clips
        rig, actions, rig_report = inspect_skeleton(objects, meshes)
    bpy.context.view_layer.update()
    low, high = Vector((math.inf,) * 3), Vector((-math.inf,) * 3)
    bounds_meshes = meshes
    if profile == "rigged":
        bounds_meshes = [mesh for mesh in meshes if any(mod.type == "ARMATURE" and mod.object == rig
                                                       for mod in mesh.modifiers)]
    for obj in bounds_meshes:
        for vertex in obj.data.vertices:
            point = obj.matrix_world @ vertex.co
            for axis in range(3):
                low[axis], high[axis] = min(low[axis], point[axis]), max(high[axis], point[axis])
    dimensions = high - low
    if not all(math.isfinite(value) for value in (*low, *high)) or max(dimensions) < 1e-8:
        raise ValueError("Imported asset has nonfinite or degenerate bounds")
    materials = {slot.material for obj in meshes for slot in obj.material_slots if slot.material}
    texture_nodes = [node for mat in materials if mat.use_nodes for node in mat.node_tree.nodes if node.type == "TEX_IMAGE"]
    images = {node.image for node in texture_nodes if node.image}
    missing = [f"unbound image node: {node.name}" for node in texture_nodes if node.image is None]
    textures = []
    for image in sorted(images, key=lambda image: image.name):
        size = list(image.size)  # Access forces Blender to decode lazily loaded packed images.
        if not image.has_data or not all(size):
            missing.append(image.name)
        textures.append({"name": image.name, "size": size, "packed": bool(image.packed_file)})
    polygon_count = sum(len(obj.data.polygons) for obj in meshes)
    if polygon_count == 0:
        raise ValueError("GLB contains no renderable surface polygons")
    report = {"mesh_count": len(meshes), "object_count": len(objects),
              "polygon_count": polygon_count,
              "bounds": {"min": list(low), "max": list(high)}, "dimensions": list(dimensions),
              "material_count": len(materials), "materials": sorted(mat.name for mat in materials),
              "texture_count": len(images), "textures": textures,
              "missing_textures": missing, "skeleton_count": 0, "animation_count": 0,
              "coordinate_system": "right-handed Z-up meters", **rig_report}
    # Reserve the public entity name independently of names inside the imported file.
    for index, obj in enumerate(objects):
        if profile == "rigged":
            obj["atlas_source_name"] = obj.name
        obj.name = f"__{identifier}_part_{index}"
    root = bpy.data.objects.new(identifier, None)
    bpy.context.scene.collection.objects.link(root)
    normalization = bpy.data.objects.new(f"__{identifier}_normalization", None)
    bpy.context.scene.collection.objects.link(normalization)
    normalization.parent = root
    for obj in objects:
        if obj.parent not in objects:
            world = obj.matrix_world.copy()
            obj.parent = normalization
            obj.matrix_world = world
    factor = 1 / max(dimensions) if normalize == "unit" else 1
    origin = Vector((0, 0, 0))
    if pivot in {"center", "base"}:
        origin = (low + high) / 2
        if pivot == "base":
            origin.z = low.z
    normalization.scale = (factor,) * 3
    normalization.location = -origin * factor
    if profile == "rigged":
        play_clips(rig, actions, clips, fps or previous_fps)
    report["normalization"] = {"profile": "atlas-parent-transform-1", "scale": factor, "origin": list(origin)}
    bpy.context.view_layer.update()
    report["import_seconds"] = time.perf_counter() - started
    return root, report
