"""Joint-landmark calibration and optional category-specific arm refinement."""
import math
from dataclasses import dataclass


SIDES = ("left", "right")
PARTS = ("upper_arm", "forearm", "hand")
DIGITS = ("thumb", "index", "middle", "ring", "pinky")
MAPPING_VERSION = "kaykit-mpfb-anatomy-1"


@dataclass(frozen=True)
class ArmProfile:
    lateral_min: float
    lateral_max: float
    swing_max: float
    elbow_min: float
    elbow_max: float
    wrist_share: float


PROFILES = {
    "idle": ArmProfile(4, 11, 22, 8, 32, .12),
    "walk": ArmProfile(4, 15, 35, 8, 38, .20),
    "run": ArmProfile(4, 20, 62, 46, 105, .22),
    "sit": ArmProfile(4, 25, 72, 9, 90, .35),
}


def refinement_profile(category, refinement):
    return PROFILES.get(category) if refinement == "category" else None


def _clamp(value, lower, upper):
    return max(lower, min(upper, value))


def arm_direction(vector, sign, profile):
    """Keep signed fore/aft swing while limiting category-specific abduction."""
    x, y, z = vector
    out = math.degrees(math.atan2(sign * x, math.hypot(y, z)))
    swing = math.degrees(math.atan2(-y, max(.15, -z)))
    a = math.radians(profile.lateral_min + (profile.lateral_max - profile.lateral_min) * _clamp(out / 90, 0, 1))
    b = math.radians(profile.swing_max * math.tanh(swing / profile.swing_max))
    return sign * math.sin(a), -math.sin(b) * math.cos(a), -math.cos(b) * math.cos(a)


def elbow_flexion(observed, profile):
    return profile.elbow_min + (profile.elbow_max - profile.elbow_min) * _clamp(observed / 150, 0, 1)


def anatomical_roles(rig, mapping):
    """Resolve named landmarks and independently validate their hierarchy."""
    result = dict(mapping)
    bones = rig.data.bones
    is_mpfb = mapping["pelvis"] == "pelvis"

    def descends(child, parent):
        return any(bone.name == parent for bone in bones[child].parent_recursive)

    for side, suffix, sign in zip(SIDES, ("l", "r"), (1, -1)):
        upper, fore, hand = (mapping[f"{side}_{part}"] for part in PARTS)
        wrist = mapping.get(f"{side}_wrist", hand if is_mpfb else f"wrist.{suffix}")
        if (wrist not in bones or not descends(fore, upper) or not descends(wrist, fore)
                or (wrist != hand and not descends(hand, wrist))):
            raise ValueError(f"Invalid {side} shoulder, elbow and wrist ancestry")
        center = (rig.matrix_world @ bones[mapping["chest"]].head_local).x
        if sign * ((rig.matrix_world @ bones[upper].head_local).x - center) <= .03:
            raise ValueError(f"Invalid {side} shoulder orientation")
        result[f"{side}_shoulder"] = upper
        result[f"{side}_elbow"] = fore
        result[f"{side}_wrist"] = wrist
        result[f"{side}_knee"] = mapping[f"{side}_shin"]
        result[f"{side}_ankle"] = mapping[f"{side}_foot"]
        collar = mapping.get(f"{side}_clavicle", f"clavicle_{suffix}" if is_mpfb else None)
        if collar:
            if collar not in bones or not descends(upper, collar) or not descends(collar, mapping["chest"]):
                raise ValueError(f"Invalid {side} clavicle ancestry")
            result[f"{side}_clavicle"] = collar
        if is_mpfb:
            for digit in DIGITS:
                parent = hand
                for index in range(1, 4):
                    name = f"{digit}_{index:02}_{suffix}"
                    if name not in bones or not descends(name, parent):
                        raise ValueError(f"Invalid {side} {digit} chain")
                    result[f"{side}_{digit}_{index}"] = name
                    parent = name
    return result


def joint_frame(direction, hint):
    """Return a proper rotation with +Y along the segment and +Z toward the hint."""
    from mathutils import Matrix, Vector

    y = direction.normalized()
    if y.length < .99:
        raise ValueError("Anatomical segment has no measurable direction")
    if abs(y.dot(hint.normalized())) > .98:
        hint = min((Vector((0, 0, 1)), Vector((1, 0, 0)), Vector((0, -1, 0))),
                   key=lambda axis: abs(axis.dot(y)))
    x = y.cross(hint).normalized()
    z = x.cross(y).normalized()
    return Matrix((x, y, z)).transposed().to_quaternion()


def rest_frames(rig, roles):
    from mathutils import Vector

    bones = rig.data.bones
    world = rig.matrix_world
    forward = Vector((0, -1, 0))
    frames = {}
    for side in SIDES:
        upper, fore, hand = (bones[roles[f"{side}_{part}"]] for part in PARTS)
        wrist = bones[roles[f"{side}_wrist"]]
        frames[f"{side}_upper_arm"] = joint_frame(world.to_3x3() @ (fore.head_local - upper.head_local), forward)
        frames[f"{side}_forearm"] = joint_frame(world.to_3x3() @ (wrist.head_local - fore.head_local), forward)
        if f"{side}_middle_1" in roles:
            middle = bones[roles[f"{side}_middle_1"]].head_local
            index = bones[roles[f"{side}_index_1"]].head_local
            pinky = bones[roles[f"{side}_pinky_1"]].head_local
            frames[f"{side}_hand"] = joint_frame(world.to_3x3() @ (middle - hand.head_local),
                                                world.to_3x3() @ (index - pinky))
        elif f"{side}_palm_axis" in roles:
            digit = bones[roles[f"{side}_palm_axis"]]
            frames[f"{side}_hand"] = joint_frame(world.to_3x3() @ (digit.head_local - hand.head_local), forward)
        else:
            frames[f"{side}_hand"] = joint_frame(world.to_3x3() @ (hand.tail_local - hand.head_local), forward)
    return frames


def calibrated_offset(source_reference, target_reference, target_rest):
    """Align complete joint frames, including roll, in a common bind pose."""
    return source_reference @ target_reference.inverted() @ target_rest


def refine_arms(raw, target_frames, target_rest, chest, profile):
    from mathutils import Vector

    forward = chest @ Vector((0, -1, 0))
    y_axis = Vector((0, 1, 0))
    desired = {}
    for side, sign in zip(SIDES, (1, -1)):
        upper, fore, hand = (f"{side}_{part}" for part in PARTS)
        observed = [(raw[key] @ target_rest[key].inverted() @ target_frames[key]) @ y_axis for key in (upper, fore)]
        direction = chest @ Vector(arm_direction(chest.inverted() @ observed[0], sign, profile))
        hinge = forward - direction * forward.dot(direction)
        if hinge.length < .1:
            hinge = chest @ Vector((0, 0, 1))
            hinge -= direction * hinge.dot(direction)
        elbow = math.radians(elbow_flexion(math.degrees(observed[0].angle(observed[1])), profile))
        flex = hinge.normalized()
        lower = direction * math.cos(elbow) + flex * math.sin(elbow)
        normal = direction.cross(flex).normalized()
        for key, axis in ((upper, direction), (fore, lower)):
            desired[key] = joint_frame(axis, normal.cross(axis)) @ target_frames[key].inverted() @ target_rest[key]
        collar_to_wrist = target_rest[fore].inverted() @ target_rest[hand]
        neutral = desired[fore] @ collar_to_wrist
        carried = desired[fore] @ raw[fore].inverted() @ raw[hand]
        deviation = 2 * math.acos(min(1., abs(neutral.normalized().dot(carried.normalized()))))
        blend = min(profile.wrist_share, math.radians(23) / deviation) if deviation > 1e-6 else profile.wrist_share
        desired[hand] = neutral.slerp(carried, blend)
    return desired


def evaluated_angles(rig, roles, frames, base):
    from mathutils import Vector

    result = {}
    axis = Vector((0, 1, 0))
    for side in SIDES:
        upper, fore, hand = (f"{side}_{part}" for part in PARTS)
        directions = []
        for key in (upper, fore, hand):
            pose = rig.matrix_world.to_quaternion() @ rig.pose.bones[roles[key]].matrix.to_quaternion()
            directions.append((pose @ base[key].inverted() @ frames[key]) @ axis)
        u, f, h = directions
        result[side] = {"lateral_deg": math.degrees(math.asin(min(1., abs(u.x)))),
                        "elbow_deg": math.degrees(u.angle(f)), "wrist_deg": math.degrees(f.angle(h))}
    return result
