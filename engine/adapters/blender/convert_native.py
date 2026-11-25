"""Factory-startup Blender worker for the bounded static native conversion profile."""
import json
import math
import struct
import sys
from pathlib import Path

import bpy


MAX_OBJECTS = 512
MAX_VERTICES = 2_000_000
MAX_TRIANGLES = 2_000_000
MAX_MATERIALS = 128
MAX_TEXTURES = 32
MAX_TEXTURE_BYTES = 32 * 1024 * 1024
MAX_TEXTURE_EDGE = 4096
MAX_TEXTURE_PIXELS = 64 * 1024 * 1024
SHADER_NODES = {"OUTPUT_MATERIAL", "BSDF_PRINCIPLED", "TEX_IMAGE", "NORMAL_MAP", "UVMAP",
                "SEPARATE_COLOR", "SEPRGB", "COMBINE_COLOR", "COMBRGB", "FRAME", "REROUTE",
                "MAPPING", "TEX_COORD"}
PBR_TEXTURES = {"Base Color": "baseColorTexture", "Alpha": "baseColorTexture",
                "Metallic": "metallicRoughnessTexture", "Roughness": "metallicRoughnessTexture",
                "Normal": "normalTexture", "Emission Color": "emissiveTexture"}


def _exr_size(payload):
    # Review the scanline header before the EXR decoder can allocate image buffers.
    header = payload[:65536]
    if header[:8] != b"v/1\x01\x02\0\0\0":
        raise ValueError("Packed OpenEXR must be a single-part scanline image")
    attributes = {}
    index = 8
    while index < len(header) and header[index] != 0:
        name_end = header.find(b"\0", index, index + 32)
        type_end = header.find(b"\0", name_end + 1, name_end + 33) if name_end >= index else -1
        if type_end < 0 or type_end + 5 > len(header):
            raise ValueError("Packed OpenEXR has an invalid attribute header")
        size = struct.unpack_from("<I", header, type_end + 1)[0]
        end = type_end + 5 + size
        name = header[index:name_end]
        if end > len(header) or name in attributes:
            raise ValueError("Packed OpenEXR header exceeds its bounds or repeats attributes")
        attributes[name] = header[name_end + 1:type_end], header[type_end + 5:end]
        index = end
    display = attributes.get(b"displayWindow")
    data = attributes.get(b"dataWindow")
    if (index >= len(header) or data is None or data != display or data[0] != b"box2i" or len(data[1]) != 16):
        raise ValueError("Packed OpenEXR requires matching scanline data and display windows")
    x_min, y_min, x_max, y_max = struct.unpack("<iiii", data[1])
    if (x_min, y_min) != (0, 0):
        raise ValueError("Packed OpenEXR requires an origin-aligned image window")
    kind, channels = attributes.get(b"channels", (None, b""))
    if kind != b"chlist" or len(channels) not in {19, 37, 55, 73} or channels[-1:] != b"\0":
        raise ValueError("Packed OpenEXR requires one to four standard color channels")
    channel_names = set()
    for offset in range(0, len(channels) - 1, 18):
        name = channels[offset:offset + 2]
        pixel_type, sx, sy = struct.unpack_from("<i4xii", channels, offset + 2)
        if name not in {b"R\0", b"G\0", b"B\0", b"A\0", b"Y\0"} or name in channel_names:
            raise ValueError("Packed OpenEXR contains a duplicate or unsupported color channel")
        if pixel_type not in {1, 2} or (sx, sy) != (1, 1):
            raise ValueError("Packed OpenEXR requires fixed-rate half- or full-float color channels")
        channel_names.add(name)
    return x_max + 1, y_max + 1


def _texture_size(payload):
    if len(payload) >= 33 and payload.startswith(b"\x89PNG\r\n\x1a\n\0\0\0\rIHDR"):
        return struct.unpack_from(">II", payload, 16), ".png"
    if payload.startswith(b"\xff\xd8"):
        index = 2
        while index + 4 <= len(payload) and payload[index] == 255:
            while index + 1 < len(payload) and payload[index + 1] == 255:
                index += 1
            if index + 4 > len(payload):
                break
            marker = payload[index + 1]
            length = int.from_bytes(payload[index + 2:index + 4], "big")
            if length < 2 or index + length + 2 > len(payload) or marker in {0xDA, 0xD9}:
                break
            if marker in {0xC0, 0xC1, 0xC2} and length >= 8:
                height, width = struct.unpack_from(">HH", payload, index + 5)
                return (width, height), ".jpg"
            index += length + 2
    if payload.startswith(b"v/1\x01"):
        return _exr_size(payload), ".exr"
    raise ValueError("Packed textures require valid PNG, JPEG or scanline OpenEXR headers")


def _check_texture(image, workspace, remaining_pixels):
    if image.source != "FILE" or len(image.packed_files) != 1:
        raise ValueError(f"Image {image.name!r} must be a single packed texture; external paths are rejected")
    packed = image.packed_file
    if packed is None or not 16 <= packed.size <= MAX_TEXTURE_BYTES:
        raise ValueError(f"Image {image.name!r} exceeds the packed texture byte budget")
    size, suffix = _texture_size(packed.data)
    if min(size) < 1 or max(size) > MAX_TEXTURE_EDGE:
        raise ValueError(f"Image {image.name!r} exceeds the packed texture dimension budget")
    if math.prod(size) > remaining_pixels:
        raise ValueError("Selected textures exceed the combined pixel budget")
    # Remove the original filename before Blender's lazy decode can fall back to disk.
    image.filepath_raw = str(workspace / f"packed-image{suffix}")
    if tuple(image.size) != size or not image.has_data:
        raise ValueError(f"Image {image.name!r} could not be decoded from the packed bytes")
    return size


def _upstream(socket):
    visited = set()
    while socket.is_linked:
        source = socket.links[0].from_socket
        if source.node.type != "REROUTE":
            return source
        if source.node in visited:
            raise ValueError("Material has cyclic reroutes")
        visited.add(source.node)
        socket = source.node.inputs[0]
    return None


def _check_coordinates(texture):
    coordinates = _upstream(texture.inputs["Vector"])
    if coordinates and coordinates.node.type == "MAPPING":
        mapping = coordinates.node
        expected = {"Location": (0, 0, 0), "Rotation": (0, 0, 0), "Scale": (1, 1, 1)}
        if mapping.vector_type != "POINT" or any(mapping.inputs[name].is_linked or
                tuple(mapping.inputs[name].default_value) != value for name, value in expected.items()):
            raise ValueError(f"Texture {texture.name!r} requires an identity UV mapping")
        coordinates = _upstream(mapping.inputs["Vector"])
        if coordinates is None:
            raise ValueError(f"Texture {texture.name!r} has no UV input for its mapping")
    if coordinates and (coordinates.name != "UV" or coordinates.node.type not in {"UVMAP", "TEX_COORD"}):
        raise ValueError(f"Texture {texture.name!r} requires UV coordinates")


def _check_materials(materials, workspace):
    if len(materials) > MAX_MATERIALS:
        raise ValueError("Selected meshes exceed the native material budget")
    images, expected_textures = set(), {}
    for material in materials:
        tree = material.node_tree
        if material.animation_data or (tree and tree.animation_data):
            raise ValueError(f"Material {material.name!r} has animation or drivers")
        expected_textures[material.name] = []
        if tree is None:
            continue
        if len(tree.nodes) > 64 or any(node.type not in SHADER_NODES for node in tree.nodes):
            raise ValueError(f"Material {material.name!r} has nodes outside the static Principled PBR profile")
        outputs = [node for node in tree.nodes if node.type == "OUTPUT_MATERIAL" and node.is_active_output]
        if len(outputs) != 1:
            raise ValueError(f"Material {material.name!r} requires one active output")
        output = outputs[0]
        surface = output.inputs["Surface"].links
        if (len(surface) != 1 or surface[0].from_node.type != "BSDF_PRINCIPLED"
                or any(socket.is_linked for socket in output.inputs if socket.name != "Surface")):
            raise ValueError(f"Material {material.name!r} requires a direct Principled surface")
        channels = set()
        for socket in surface[0].from_node.inputs:
            if socket.is_linked:
                if socket.name not in PBR_TEXTURES:
                    raise ValueError(f"Material {material.name!r} uses an unsupported Principled input {socket.name!r}")
                channels.add(PBR_TEXTURES[socket.name])
        expected_textures[material.name] = sorted(channels)
        for node in tree.nodes:
            if node.type == "TEX_IMAGE":
                if node.image is None:
                    raise ValueError(f"Material {material.name!r} has an unbound image texture")
                _check_coordinates(node)
                images.add(node.image)

    if len(images) > MAX_TEXTURES:
        raise ValueError("Selected materials exceed the native texture count budget")
    remaining_pixels = MAX_TEXTURE_PIXELS
    for image in sorted(images, key=lambda item: item.name):
        size = _check_texture(image, workspace, remaining_pixels)
        remaining_pixels -= math.prod(size)
    return len(images), expected_textures


def _check_provider_markers(objects, provider_asset_id):
    metadata = [obj["asset_data"] for obj in objects if "asset_data" in obj]
    for entry in metadata:
        if (not hasattr(entry, "get") or entry.get("assetBaseId") != provider_asset_id
                or entry.get("isFree") is not True or entry.get("license") != "cc_zero"):
            raise ValueError("Embedded Blendkit metadata does not match the reviewed Free-plan CC0 asset")
    return bool(metadata)


def _append(source, selection):
    kind, names = next(iter(selection.items()))
    with bpy.data.libraries.load(str(source), link=False) as (available, requested):
        if getattr(available, "libraries", ()):
            raise ValueError("Native source depends on linked libraries")
        if available.texts:
            raise ValueError("Native source contains embedded text blocks")
        if missing := set(names) - set(getattr(available, kind)):
            raise ValueError(f"Selected {kind} were not found: {', '.join(sorted(missing))}")
        source_version = list(getattr(available, "version", ()))
        setattr(requested, kind, names)
    selected = getattr(requested, kind)
    # Append records the source library for reuse even when every imported ID is local.
    if (any(item is None for item in selected) or bpy.data.texts
            or any(Path(library.filepath) != source for library in bpy.data.libraries)
            or any(block.library is not None for block in bpy.data.user_map())):
        raise ValueError("Native selection failed to append as local, script-free data")
    if kind == "objects":
        return selected, set(selected), source_version
    objects = {obj for collection in selected for obj in collection.all_objects}
    return selected, objects, source_version


def _check_objects(objects):
    if len(objects) > MAX_OBJECTS:
        raise ValueError("Selection exceeds the native object count budget")
    meshes, materials = [], set()
    triangles, vertices = 0, 0
    for obj in sorted(objects, key=lambda item: item.name):
        if obj.type not in {"MESH", "EMPTY"} or obj.instance_type != "NONE":
            raise ValueError(f"Object {obj.name!r} is not an uninstanced mesh or empty")
        if obj.parent and (obj.parent not in objects or obj.parent_type != "OBJECT"):
            raise ValueError(f"Object {obj.name!r} requires its parent in the native selection")
        if obj.animation_data or obj.constraints or obj.particle_systems:
            raise ValueError(f"Object {obj.name!r} has animation, drivers, constraints or particles")
        if obj.hide_render or obj.hide_viewport:
            raise ValueError(f"Object {obj.name!r} is disabled for rendering or viewport evaluation")
        if any(not math.isfinite(value) for row in obj.matrix_basis for value in row):
            raise ValueError(f"Object {obj.name!r} has a nonfinite transform")
        if obj.type == "EMPTY":
            if obj.data is not None:
                raise ValueError(f"Empty {obj.name!r} contains unsupported data such as a reference image")
            continue
        mesh = obj.data
        if mesh.animation_data or mesh.shape_keys or len(mesh.uv_layers) > 8:
            raise ValueError(f"Mesh {obj.name!r} has animation, shape keys or too many UV sets")
        if (len(obj.modifiers) > 1 or any(mod.type != "TRIANGULATE" or not mod.show_viewport or not mod.show_render
                                        for mod in obj.modifiers)):
            raise ValueError(f"Mesh {obj.name!r} has modifiers outside the static triangulation profile")
        if not mesh.polygons:
            raise ValueError(f"Mesh {obj.name!r} has no surface polygons")
        meshes.append(obj)
        vertices += len(mesh.vertices)
        triangles += len(mesh.loops) - 2 * len(mesh.polygons)
        if vertices > MAX_VERTICES or triangles > MAX_TRIANGLES:
            raise ValueError("Selected meshes exceed the native vertex or triangle budget")
        slots = {poly.material_index for poly in mesh.polygons}
        materials.update(obj.material_slots[index].material for index in slots
                         if index < len(obj.material_slots) and obj.material_slots[index].material)
    if not meshes:
        raise ValueError("Native selection contains no renderable meshes")
    return meshes, materials, triangles, vertices


def convert(source, destination, selection, provider_asset_id):
    if bpy.app.online_access:
        raise RuntimeError("Native conversion requires Blender offline mode")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.use_scripts_auto_execute = False
    selected, objects, source_version = _append(source, selection)
    matched_provider_metadata = _check_provider_markers(objects, provider_asset_id)
    meshes, materials, triangles, vertices = _check_objects(objects)
    texture_count, texture_channels = _check_materials(materials, source.parent)
    target = bpy.context.scene.collection
    if "collections" in selection:
        for collection in selected:
            if collection.hide_render or collection.hide_viewport or any(
                    sub.hide_render or sub.hide_viewport for sub in collection.children_recursive):
                raise ValueError(f"Collection {collection.name!r} is disabled for rendering or viewport evaluation")
            target.children.link(collection)
    else:
        for obj in selected:
            target.objects.link(obj)
    bpy.context.view_layer.update()
    result = bpy.ops.export_scene.gltf(filepath=str(destination), export_format="GLB", export_animations=False,
        export_skins=False, export_morph=False, export_cameras=False, export_lights=False,
        export_extras=False, export_apply=any(obj.modifiers for obj in meshes), export_image_format="AUTO")
    if "FINISHED" not in result:
        raise ValueError("Blender GLB export did not finish")
    return {"blender_version": bpy.app.version_string, "source_blender_version": source_version,
            "object_count": len(objects), "mesh_count": len(meshes), "source_vertex_count": vertices,
            "source_triangle_count": triangles, "material_count": len(materials),
            "texture_count": texture_count, "material_texture_channels": texture_channels,
            "matched_embedded_blendkit_metadata": matched_provider_metadata}


def main():
    source, destination, settings, report = map(Path, sys.argv[sys.argv.index("--") + 1:])
    try:
        result = convert(source, destination, **json.loads(settings.read_text(encoding="utf-8")))
    except ValueError as exc:
        report.write_text(json.dumps({"error": str(exc)}), encoding="utf-8")
        raise
    report.write_text(json.dumps(result, allow_nan=False), encoding="utf-8")


if __name__ == "__main__":
    main()
