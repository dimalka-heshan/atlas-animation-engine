"""Bounded GLB container inspection before invoking Blender's importer.

This is a conservative capability boundary, not a complete glTF schema validator.
Only embedded static meshes without extensions are supported in this release.
"""
import json
import struct
from pathlib import Path

MAX_GLB_BYTES = 256 * 1024 * 1024
MAX_JSON_BYTES = 8 * 1024 * 1024


def inspect_glb(path: Path) -> dict:
    size = path.stat().st_size
    if not 20 <= size <= MAX_GLB_BYTES:
        raise ValueError("GLB size must be between 20 bytes and 256 MiB")
    with path.open("rb") as handle:
        magic, version, declared_size = struct.unpack("<4sII", handle.read(12))
        if magic != b"glTF" or version != 2 or declared_size != size:
            raise ValueError("Invalid GLB magic, version or declared length")
        chunks = []
        document = None
        binary_size = 0
        while handle.tell() < size:
            header = handle.read(8)
            if len(header) != 8:
                raise ValueError("Truncated GLB chunk header")
            length, kind = struct.unpack("<II", header)
            if length % 4 or length > size - handle.tell():
                raise ValueError("Invalid GLB chunk length")
            chunks.append(kind)
            if kind == 0x4E4F534A and len(chunks) == 1:
                if length > MAX_JSON_BYTES:
                    raise ValueError("GLB JSON chunk exceeds 8 MiB")
                try:
                    document = json.loads(handle.read(length).decode("utf-8"),
                                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
                except (ValueError, UnicodeError, RecursionError) as exc:
                    raise ValueError("Invalid GLB JSON chunk") from exc
            elif kind == 0x004E4942 and len(chunks) == 2:
                binary_size = length
                handle.seek(length, 1)
            else:
                raise ValueError("Unsupported GLB chunk order or type")
    if (not isinstance(document, dict) or not isinstance(document.get("asset"), dict)
            or document["asset"].get("version") != "2.0"):
        raise ValueError("GLB must contain a glTF 2.0 JSON document")
    try:
        return _inspect_document(document, binary_size, size)
    except (TypeError, KeyError, AttributeError, IndexError, RecursionError) as exc:
        raise ValueError("Malformed GLB document structure") from exc


def _inspect_document(doc: dict, binary_size: int, size: int) -> dict:
    def walk(value):
        if isinstance(value, dict):
            if "uri" in value:
                raise ValueError("GLB contains a URI dependency; only embedded BIN/bufferView resources are supported")
            if value.get("extensions"):
                raise ValueError("GLB extensions are not supported by this importer profile")
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(doc)
    if doc.get("extensionsUsed") or doc.get("extensionsRequired"):
        raise ValueError("GLB extensions are not supported by this importer profile")
    if doc.get("animations") or doc.get("skins"):
        raise ValueError("Animated/skinned GLBs are unsupported; use a static mesh asset")
    _check_scene(doc)
    buffers = doc.get("buffers", [])
    if len(buffers) > 1:
        raise ValueError("GLB must have at most one embedded buffer")
    if buffers:
        length = buffers[0]["byteLength"]
        if type(length) is not int or length < 0 or not length <= binary_size <= length + 3:
            raise ValueError("GLB binary buffer length mismatch")
    elif binary_size:
        raise ValueError("GLB BIN chunk has no buffer declaration")
    for view in doc.get("bufferViews", []):
        offset, length = view.get("byteOffset", 0), view["byteLength"]
        if (view["buffer"] != 0 or not buffers or type(offset) is not int or type(length) is not int
                or offset < 0 or length < 1 or offset + length > buffers[0]["byteLength"]):
            raise ValueError("GLB bufferView lies outside embedded buffer")
    for image in doc.get("images", []):
        view = image["bufferView"]
        if (type(view) is not int or not 0 <= view < len(doc.get("bufferViews", []))
                or image["mimeType"] not in {"image/png", "image/jpeg"}):
            raise ValueError("GLB image must reference an embedded PNG/JPEG bufferView")
    for texture in doc.get("textures", []):
        source = texture.get("source")
        if type(source) is not int or not 0 <= source < len(doc.get("images", [])):
            raise ValueError("GLB texture has a missing or invalid image source")
    def check_texture_info(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key.endswith("Texture"):
                    index = item.get("index")
                    if type(index) is not int or not 0 <= index < len(doc.get("textures", [])):
                        raise ValueError("GLB material has a missing or invalid texture reference")
                check_texture_info(item)
        elif isinstance(value, list):
            for item in value:
                check_texture_info(item)
    check_texture_info(doc.get("materials", []))
    for mesh in doc.get("meshes", []):
        for primitive in mesh["primitives"]:
            if primitive.get("mode", 4) != 4:
                raise ValueError("Only triangle-surface GLB primitives are supported")
            if primitive.get("targets"):
                raise ValueError("GLB morph targets are not supported")
    return {"format": "glb", "gltf_version": "2.0", "size_bytes": size,
            "mesh_count": len(doc.get("meshes", [])), "material_count": len(doc.get("materials", [])),
            "texture_count": len(doc.get("images", [])), "animation_count": 0, "skin_count": 0,
            "external_dependencies": []}


def _check_scene(doc: dict) -> None:
    """Blender may import unmatched nodes; reject them before importer execution."""
    nodes, scenes = doc.get("nodes", []), doc.get("scenes", [])
    if not isinstance(nodes, list) or not isinstance(scenes, list):
        raise ValueError("GLB nodes and scenes must be arrays")
    if doc.get("cameras"):
        raise ValueError("GLB cameras are unsupported; use project camera settings")
    if not nodes and not scenes:
        return  # Registration may store an empty container; inspection will reject no geometry.
    if len(scenes) != 1 or doc.get("scene", 0) != 0 or len(nodes) > 10000:
        raise ValueError("GLB must contain one default scene with at most 10000 reachable nodes")
    roots = scenes[0].get("nodes", [])
    parents = [0] * len(nodes)
    def valid_index(index):
        if type(index) is not int or not 0 <= index < len(nodes):
            raise ValueError("GLB scene has an invalid node reference")
    for node in nodes:
        if "camera" in node or "skin" in node:
            raise ValueError("GLB camera/skin nodes are unsupported")
        for child in node.get("children", []):
            valid_index(child)
            parents[child] += 1
            if parents[child] > 1:
                raise ValueError("GLB nodes must form a tree without shared children")
    for root in roots:
        valid_index(root)
        if parents[root]:
            raise ValueError("GLB scene roots cannot also be child nodes")
    visited, pending = set(), list(roots)
    while pending:
        index = pending.pop()
        if index in visited:
            raise ValueError("GLB scene has duplicate or cyclic node references")
        visited.add(index)
        pending.extend(nodes[index].get("children", []))
    if len(visited) != len(nodes):
        raise ValueError("GLB contains nodes outside its default scene")
