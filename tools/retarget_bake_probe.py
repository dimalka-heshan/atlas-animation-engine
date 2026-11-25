"""Compare KayKit source, MPFB bind/native poses and a directly played ATLAS bake."""
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine/adapters/blender"))
from asset_import import import_asset
from bake_motion import armature
from motion_playback import materialize


def imported(path, name, profile, clip=None):
    events = [{"name": clip, "start_frame": 1, "frame_count": 24, "loop": True,
               "speed": 1, "blend_frames": 0}] if clip else []
    root, report = import_asset(path, name, pivot="base", profile=profile, fps=30, clips=events)
    rig = armature(root)
    if clip:
        track = rig.animation_data.nla_tracks[0]
        strip = track.strips[0]
        action, slot = strip.action, strip.action_slot
        rig.animation_data.nla_tracks.remove(track)
        rig.animation_data.action = action
        rig.animation_data.action_slot = slot
    return rig, report


def sample(rig, roles):
    result = {}
    world = rig.matrix_world
    for side in ("left", "right"):
        upper, forearm, hand = (rig.pose.bones[roles[f"{side}_{part}"]] for part in ("upper_arm", "forearm", "hand"))
        upper_direction = world.to_3x3() @ (forearm.head - upper.head)
        lower_direction = world.to_3x3() @ (hand.head - forearm.head)
        hand_direction = world.to_3x3() @ (hand.tail - hand.head)
        result[side] = {
            "upper_direction": list(upper_direction.normalized()),
            "lateral_deg": math.degrees(math.asin(min(1., abs(upper_direction.normalized().x)))),
            "elbow_deg": math.degrees(upper_direction.angle(lower_direction)),
            "hand_tail_deg": math.degrees(lower_direction.angle(hand_direction)),
            "rest_tail_to_next_joint_deg": [
                math.degrees((bone.tail_local - bone.head_local).angle(child.head_local - bone.head_local))
                for bone, child in ((upper.bone, forearm.bone), (forearm.bone, hand.bone))],
        }
    return result


def main():
    spec = json.loads(Path(sys.argv[-1]).read_text(encoding="utf-8"))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps = 30
    source, source_meta = imported(spec["source"], "source", "rigged", spec.get("source_clip", "Walking_A"))
    rest, rest_meta = imported(spec["target"], "rest", "human")
    native, native_meta = imported(spec["target"], "native", "human", spec.get("native_clip", "HumanIdle"))
    baked, baked_meta = imported(spec["target"], "baked", "human")
    record = json.loads(Path(spec["motion"]).read_text(encoding="utf-8"))
    action, slot, _, _ = materialize(baked, {"motion": {"id": "audit"}}, record, baked_meta["skeleton_sha256"])
    baked.animation_data.action = action
    baked.animation_data.action_slot = slot
    count = len(record["bake"]["frames"])
    first = int(record["source"]["frames"][0])
    stages = {"source": (source, source_meta, range(first, first + count)),
              "target_rest": (rest, rest_meta, [0]), "target_native": (native, native_meta, range(count)),
              "direct_bake": (baked, baked_meta, range(count))}
    measured = {}
    for name, (rig, report, frames) in stages.items():
        measured[name] = {}
        for frame in frames:
            scene.frame_set(frame)
            bpy.context.view_layer.update()
            measured[name][frame] = sample(rig, report["humanoid_mapping"])
    Path(spec["output"]).write_text(json.dumps(measured, indent=2), encoding="utf-8")
    print("ATLAS_RETARGET_BAKE_EVALUATED")


if __name__ == "__main__":
    main()
