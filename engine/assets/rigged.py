"""Conservative skeletal GLB preflight, separate from the static profile."""
import math


def validate_rigged(doc: dict, *, facial=False) -> None:
    nodes, meshes = doc["nodes"], doc["meshes"]
    skins, animations = doc["skins"], doc.get("animations", [])
    accessors, views = doc["accessors"], doc["bufferViews"]
    if len(skins) != 1 or not 1 <= len(animations) <= 128 or len(accessors) > 40000:
        raise ValueError("Rigged profile requires one embedded skin and 1–128 animations")

    def index(items, number):
        if type(number) is not int or not 0 <= number < len(items):
            raise ValueError("Invalid rigged GLB index")
        return items[number]

    widths = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
    sizes = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}
    for accessor in accessors:
        if "sparse" in accessor:
            raise ValueError("Sparse rigged accessors are unsupported")
        view = index(views, accessor["bufferView"])
        component_size = sizes[accessor["componentType"]]
        element = component_size * widths[accessor["type"]]
        offset, count = accessor.get("byteOffset", 0), accessor["count"]
        stride = view.get("byteStride", element)
        if (type(offset) is not int or type(count) is not int or type(stride) is not int or offset < 0
                or not 1 <= count <= 2_000_000 or stride < element or stride > 252
                or offset + (count - 1) * stride + element > view["byteLength"]):
            raise ValueError("Rigged GLB accessor exceeds its bufferView")

    joints = skins[0]["joints"]
    if not 2 <= len(joints) <= 256 or len(set(joints)) != len(joints):
        raise ValueError("Rigged GLB has an invalid joint list")
    names = [index(nodes, joint).get("name") for joint in joints]
    if any(not isinstance(name, str) or not name or len(name) > 63 for name in names) or len(set(names)) != len(names):
        raise ValueError("Rigged GLB requires unique named joints")
    inverse = index(accessors, skins[0]["inverseBindMatrices"])
    if inverse["type"] != "MAT4" or inverse["componentType"] != 5126 or inverse["count"] != len(joints):
        raise ValueError("Invalid inverse bind matrices")
    skinned = 0
    for node in nodes:
        if "mesh" not in node:
            if "skin" in node:
                raise ValueError("Skin requires a mesh")
            continue
        mesh = index(meshes, node["mesh"])
        if "skin" not in node:
            continue
        index(skins, node["skin"])
        skinned += 1
        for primitive in mesh["primitives"]:
            attrs = primitive["attributes"]
            position, joint, weight = (index(accessors, attrs[key]) for key in ("POSITION", "JOINTS_0", "WEIGHTS_0"))
            if (joint["type"] != "VEC4" or joint["componentType"] not in {5121, 5123}
                    or weight["type"] != "VEC4" or weight["componentType"] not in {5121, 5123, 5126}
                    or not joint["count"] == weight["count"] == position["count"]):
                raise ValueError("Invalid skin weight accessors")
    if not skinned:
        raise ValueError("Rigged GLB contains no skinned meshes")
    if facial:
        from engine.adapters.blender.human_controls import HUMAN_KEYS
        faces = 0
        total_morph_vectors = 0
        for mesh in meshes:
            names = mesh.get("extras", {}).get("targetNames", [])
            if len(names) > len(HUMAN_KEYS) or len(set(names)) != len(names) or not set(names) <= HUMAN_KEYS:
                raise ValueError("Human GLB contains unknown or duplicate facial targets")
            faces += set(names) == HUMAN_KEYS
            for primitive in mesh["primitives"]:
                count = index(accessors, primitive["attributes"]["POSITION"])["count"]
                targets = primitive.get("targets", [])
                if len(targets) != len(names) or any(set(target) != {"POSITION"} for target in targets):
                    raise ValueError("Human GLB requires named position-only facial deltas")
                for target in targets:
                    delta = index(accessors, target["POSITION"])
                    if delta["type"] != "VEC3" or delta["componentType"] != 5126 or delta["count"] != count:
                        raise ValueError("Human GLB facial delta accessor does not match its mesh")
                    total_morph_vectors += count
                    if total_morph_vectors > 1_000_000:
                        raise ValueError("Human GLB exceeds the facial target budget")
        if faces != 1:
            raise ValueError("Human GLB must contain exactly one complete facial mesh")
    names = set()
    total_keys = 0
    for clip in animations:
        name = clip["name"]
        if not isinstance(name, str) or not name.strip() or name in names or len(name) > 63:
            raise ValueError("Invalid or duplicate skeletal clip name")
        names.add(name)
        samplers, channels = clip["samplers"], clip["channels"]
        if not 1 <= len(channels) <= 2048:
            raise ValueError("Invalid skeletal clip channel count")
        targets = set()
        clip_keys = 0
        for channel in channels:
            sampler = index(samplers, channel["sampler"])
            target = channel["target"]
            index(nodes, target["node"])
            path = target["path"]
            key = target["node"], path
            if path not in {"translation", "rotation", "scale"} or key in targets or (facial and target["node"] not in joints):
                raise ValueError("Only unique transform channels are supported")
            targets.add(key)
            points = index(accessors, sampler["input"])
            values = index(accessors, sampler["output"])
            interpolation = sampler.get("interpolation", "LINEAR")
            if (interpolation not in {"LINEAR", "STEP"} or points["type"] != "SCALAR"
                    or points["componentType"] != 5126 or values["componentType"] != 5126
                    or values["type"] != ("VEC4" if path == "rotation" else "VEC3")
                    or points["count"] != values["count"]
                    or not all(math.isfinite(x) and 0 <= x <= 600 for x in [*points["min"], *points["max"]])):
                raise ValueError("Unsupported skeletal clip sampler")
            clip_keys += points["count"]
            total_keys += points["count"]
            if clip_keys > 100_000 or total_keys > 1_000_000:
                raise ValueError("Rigged GLB exceeds the per-clip or total animation key budget")
