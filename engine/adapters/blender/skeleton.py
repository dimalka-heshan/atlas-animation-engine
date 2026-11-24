"""Inspect and play the original embedded actions on their source armature."""
import hashlib
import json
import math

from mathutils import Matrix

HUMANOID = {"root": "root", "pelvis": "hips", "spine": "spine", "chest": "chest", "head": "head"}
for side, suffix in (("left", ".l"), ("right", ".r")):
    for role, name in (("upper_arm", "upperarm"), ("forearm", "lowerarm"), ("hand", "hand"),
                       ("thigh", "upperleg"), ("shin", "lowerleg"), ("foot", "foot"), ("toes", "toes")):
        HUMANOID[f"{side}_{role}"] = name + suffix


def inspect_skeleton(objects, meshes):
    rigs = [obj for obj in objects if obj.type == "ARMATURE"]
    if len(rigs) != 1:
        raise ValueError("Expected exactly one imported armature")
    rig = rigs[0]
    skeleton = [{"name": bone.name, "parent": bone.parent.name if bone.parent else None,
                 "rest": [[round(v, 7) for v in row] for row in bone.matrix_local]}
                for bone in sorted(rig.data.bones, key=lambda item: item.name)]
    if not skeleton or any(not all(math.isfinite(value) for row in bone["rest"] for value in row) for bone in skeleton):
        raise ValueError("Missing or invalid armature rest pose")
    skin_count = 0
    for mesh in meshes:
        if not any(mod.type == "ARMATURE" and mod.object == rig for mod in mesh.modifiers):
            continue
        skin_count += 1
        valid = {group.index for group in mesh.vertex_groups if group.name in rig.data.bones}
        if not valid or any(not any(g.group in valid and 0 < g.weight <= 1 for g in v.groups) for v in mesh.data.vertices):
            raise ValueError("Skinned mesh has vertices without valid bone weights")
    if not skin_count:
        raise ValueError("The imported armature has no weighted mesh")
    for obj in objects:
        if obj != rig and obj.animation_data:
            raise ValueError("Only armature-bound actions are supported in this profile")
    data = rig.animation_data
    if not data:
        raise ValueError("Imported rig has no animation data")
    actions = {}
    for track in data.nla_tracks:
        if len(track.strips) != 1 or not track.strips[0].action:
            raise ValueError("Expected one embedded action per imported animation track")
        strip = track.strips[0]
        if track.name in actions:
            raise ValueError("Duplicate imported animation track")
        actions[track.name] = (strip.action, strip.action_slot, float(strip.action_frame_start), float(strip.action_frame_end))
    clips = [{"name": name, "source_fps": 30, "frames": [start, end], "duration_seconds": (end - start) / 30}
             for name, (_, _, start, end) in sorted(actions.items()) if end > start]
    if not clips:
        raise ValueError("Rig has no nonzero-length animation clips")
    data.action = None
    for track in list(data.nla_tracks):
        data.nla_tracks.remove(track)
    for bone in rig.pose.bones:
        bone.matrix_basis = Matrix.Identity(4)
    mapping = {}
    if all(name in rig.data.bones for name in HUMANOID.values()):
        def descends(child, ancestor):
            return ancestor in {parent.name for parent in rig.data.bones[child].parent_recursive}
        chains = [("hips", "root"), ("spine", "hips"), ("chest", "spine"), ("head", "chest")]
        for suffix in (".l", ".r"):
            chains.extend((child + suffix, parent + suffix) for child, parent in (
                ("lowerarm", "upperarm"), ("hand", "lowerarm"), ("lowerleg", "upperleg"),
                ("foot", "lowerleg"), ("toes", "foot")))
        if all(descends(child, parent) for child, parent in chains):
            mapping = HUMANOID.copy()
    return rig, actions, {
        "skeleton_count": 1, "skinned_mesh_count": skin_count, "skeleton": skeleton, "clips": clips,
        "skeleton_sha256": hashlib.sha256(json.dumps(skeleton, sort_keys=True).encode()).hexdigest(),
        "humanoid_mapping": mapping, "animation_count": len(clips),
        "facial_shape_keys": sorted({key.name for mesh in meshes if mesh.data.shape_keys
                                     for key in mesh.data.shape_keys.key_blocks if key.name != "Basis"}),
        "jaw_bones": [bone.name for bone in rig.data.bones if "jaw" in bone.name.casefold()],
    }


def play_clips(rig, actions, clips, fps):
    if not clips:
        return
    previous = None
    for clip in clips:
        name = clip["name"]
        # Give later strips precedence at a shared boundary frame. One track
        # evaluates the preceding strip first when its end equals the next start.
        track = rig.animation_data.nla_tracks.new(prev=previous)
        track.name = f"ATLAS {clip['start_frame']}: {name}"
        previous = track
        if name not in actions:
            raise ValueError(f"Unknown source-rig clip {name}")
        action, slot, source_start, source_end = actions[name]
        length = source_end - source_start
        if length <= 0:
            raise ValueError(f"Clip {name} has no duration")
        start, count = clip["start_frame"], clip["frame_count"]
        scale = fps / (30 * clip["speed"])
        repeat = count / (length * scale)
        if repeat > 1000:
            raise ValueError(f"Clip {name} exceeds the supported repeat limit")
        if repeat > 1 + 1e-6 and not clip["loop"]:
            raise ValueError(f"Nonlooping clip {name} exceeds its source duration")
        strip = track.strips.new(name, start, action)
        strip.action_slot = slot
        strip.action_frame_start, strip.action_frame_end = source_start, source_end
        strip.extrapolation = "NOTHING"
        strip.blend_type = "REPLACE"
        strip.scale = scale
        if repeat <= 1:
            strip.action_frame_end = source_start + count / scale
        else:
            strip.repeat = repeat
        strip.frame_start = start
        end = start + count
        strip.frame_end = end
        # Blender includes the terminal frame. Shorten only the raw strip
        # boundary by a subframe, leaving action scale and repeat unchanged.
        strip.frame_end_raw = end - max(.001, end / 2**22)
        strip.blend_in = clip["blend_frames"]
