"""Sample a licensed KayKit Action and bake it onto one inspected MPFB rest rig."""
import json
import math
from pathlib import Path
from statistics import median
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from asset_import import import_asset


FPS = 30
SIDES = ("left", "right")


def armature(root):
    return next(obj for obj in root.children_recursive if obj.type == "ARMATURE")


def limb_length(rig, roles):
    bones = rig.data.bones
    return sum((bones[roles[f"{side}_{a}"]].head_local - bones[roles[f"{side}_{b}"]].head_local).length
               for side in SIDES for a, b in (("thigh", "shin"), ("shin", "foot"))) / 2


def validate_axes(rig, roles):
    if any(abs(value - 1) > 1e-4 for value in rig.matrix_world.to_scale()):
        raise ValueError("The motion bake requires meter-scale armatures")
    for side in SIDES:
        foot, toes = (rig.matrix_world @ rig.data.bones[roles[f"{side}_{role}"]].head_local
                      for role in ("foot", "toes"))
        delta = toes - foot
        if delta.y >= -.035 or abs(delta.x) > abs(delta.y):
            raise ValueError("The motion bake requires the inspected -Y forward foot orientation")


def sampled_floor(shoes, groups):
    evaluated = shoes.evaluated_get(bpy.context.evaluated_depsgraph_get())
    return [min((evaluated.matrix_world @ evaluated.data.vertices[i].co).z for i in group) for group in groups]


def bake(spec):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps = FPS
    clip = spec["clip"]
    lo, hi = clip["frames"]
    source_root, source_report = import_asset(spec["source"], "source", profile="rigged", fps=FPS,
        clips=[{"name": clip["name"], "start_frame": 1, "frame_count": math.ceil(hi - lo),
                "loop": True, "speed": 1, "blend_frames": 0}])
    target_root, target_report = import_asset(spec["target"], "target", pivot="base", profile="human", fps=FPS)
    source, target = armature(source_root), armature(target_root)
    sr, tr = source_report["humanoid_mapping"], target_report["humanoid_mapping"]
    if not sr or not tr:
        raise ValueError("Motion bake requires both inspected humanoid mappings")
    for rig, roles in ((source, sr), (target, tr)):
        validate_axes(rig, roles)
    source_rot = source.matrix_world.to_quaternion()
    target_rot = target.matrix_world.to_quaternion()
    length_ratio = limb_length(target, tr) / limb_length(source, sr)
    if not .35 <= length_ratio <= 3:
        raise ValueError("Unsupported source and target leg-length ratio")
    tracks = source.animation_data.nla_tracks
    strip = tracks[0].strips[0]
    action, slot = strip.action, strip.action_slot
    tracks.remove(tracks[0])
    source.animation_data.action = action
    source.animation_data.action_slot = slot

    target_bones = sorted(target.pose.bones, key=lambda bone: (len(bone.parent_recursive), bone.name))
    by_bone = {name: role for role, name in tr.items() if role in sr and role != "root"}
    mapped = [bone.name for bone in target_bones if bone.name in by_bone]
    source_rest = {role: source_rot @ source.data.bones[name].matrix_local.to_quaternion() for role, name in sr.items()}
    target_rest = {bone.name: bone.bone.matrix_local.to_quaternion() for bone in target_bones}
    neutral = {name: target_rot @ target_rest[name] for name in mapped}
    for name in mapped:
        role = by_bone[name]
        if role.endswith(("upper_arm", "forearm", "hand")):
            src, dst = source.data.bones[sr[role]], target.data.bones[name]
            a = target_rot @ (dst.tail_local - dst.head_local).normalized()
            b = source_rot @ (src.tail_local - src.head_local).normalized()
            neutral[name] = a.rotation_difference(b) @ neutral[name]

    shoes = [obj for obj in target_root.children_recursive if obj.type == "MESH"
             and "shoes" in obj.get("atlas_source_name", "").casefold()]
    if len(shoes) != 1:
        raise ValueError("The MPFB motion profile requires one inspected shoe mesh")
    shoes = shoes[0]
    groups = [[vertex.index for vertex in shoes.data.vertices if sign * (shoes.matrix_world @ vertex.co).x > 0]
              for sign in (1, -1)]
    if not all(groups):
        raise ValueError("Could not locate separate MPFB shoe groups")

    source_root_bone, source_pelvis = (source.pose.bones[sr[role]] for role in ("root", "pelvis"))
    pelvis = target.pose.bones[tr["pelvis"]]
    pelvis_to_local = (target_rot @ target_rest[pelvis.name]).inverted()
    source_bind = source.matrix_world @ source.data.bones[sr["pelvis"]].head_local
    count = round((hi - lo) * FPS / clip["source_fps"])
    if not 1 <= count <= 360:
        raise ValueError("Motion has no playable samples or exceeds the 12-second bake limit")
    original_root = None
    frames, root_trace, contact = [], [], [[], []]
    before, after, stance_rates = [], [], []
    previous = {}
    last_feet = None
    for index in range(count + 1):
        source_frame = lo + (hi - lo) * index / count
        scene.frame_set(math.floor(source_frame), subframe=source_frame % 1)
        root_position = source.matrix_world @ source_root_bone.head
        if original_root is None:
            original_root = root_position.copy()
        displacement = root_position - original_root
        root_trace.append([round(displacement.x, 7), round(displacement.y, 7)])

        evaluated_rotation = {}
        for bone in target_bones:
            name = bone.name
            rest = target_rest[name]
            carried = evaluated_rotation[bone.parent.name] @ target_rest[bone.parent.name].inverted() @ rest if bone.parent else rest
            role = by_bone.get(name)
            if role is None:
                evaluated_rotation[name] = carried
                continue
            source_pose = source_rot @ source.pose.bones[sr[role]].matrix.to_quaternion()
            desired = target_rot.inverted() @ source_pose @ source_rest[role].inverted() @ neutral[name]
            basis = (carried.inverted() @ desired).normalized()
            if name in previous and basis.dot(previous[name]) < 0:
                basis.negate()
            previous[name] = basis.copy()
            bone.rotation_mode = "QUATERNION"
            bone.rotation_quaternion = basis
            evaluated_rotation[name] = desired

        pelvis_delta = (source.matrix_world @ source_pelvis.head) - source_bind
        pelvis_delta.x -= displacement.x
        pelvis_delta.y -= displacement.y
        pelvis_delta *= length_ratio
        pelvis.location = pelvis_to_local @ pelvis_delta
        bpy.context.view_layer.update()
        heights = sampled_floor(shoes, groups)
        floor = min(heights)
        before.append(floor)
        if spec["ground"]:
            if abs(floor) > .32:
                raise ValueError("Retargeted foot height exceeds the calibrated grounding range")
            pelvis.location += pelvis_to_local @ Vector((0, 0, -floor))
            bpy.context.view_layer.update()
            heights = sampled_floor(shoes, groups)
        after.append(min(heights))
        feet = [target.matrix_world @ target.pose.bones[tr[f"{side}_foot"]].head for side in SIDES]
        for side, height in enumerate(heights):
            if height <= min(heights) + .025:
                contact[side].append(index)
                if last_feet and index - 1 in contact[side]:
                    velocity = (feet[side].y - last_feet[side].y) * FPS
                    if velocity > 0:
                        stance_rates.append(velocity)
        last_feet = feet
        frames.append([[round(value, 8) for value in previous[name]] for name in mapped]
                      + [[round(value, 8) for value in pelvis.location]])

    root_distance = math.dist(root_trace[0], root_trace[-1])
    speed = median(stance_rates) if stance_rates and spec["category"] in {"walk", "run"} else None
    return {"fps": FPS, "bones": mapped, "pelvis": pelvis.name, "frames": frames,
            "metrics": {"leg_scale": round(length_ratio, 6), "source_root_ground_m": round(root_distance, 6),
                        "root_type": "root-motion-converted" if root_distance >= .025 else "in-place",
                        "source_root_xy": root_trace, "calibrated_speed_mps": round(speed, 6) if speed else None,
                        "ground_corrected": spec["ground"], "pre_ground_z_range_m": [min(before), max(before)],
                        "post_ground_z_range_m": [min(after), max(after)], "contact_samples": dict(zip(SIDES, contact))}}


if __name__ == "__main__":
    directory = Path(sys.argv[sys.argv.index("--") + 1])
    spec = json.loads((directory / "request.json").read_text(encoding="utf-8"))
    (directory / "bake.json").write_text(json.dumps(bake(spec), allow_nan=False), encoding="utf-8")
