"""Construct editable Blender Actions from trusted, job-local motion snapshots."""
import hashlib
import json
import math

import bpy


def read_bakes(directory):
    mapping = directory / "motion-map.json"
    if not mapping.is_file():
        return {}
    files = json.loads(mapping.read_text(encoding="utf-8"))
    bakes = {}
    for digest, entry in files.items():
        path = (directory / entry["source_file"]).resolve()
        if not path.is_relative_to(directory.resolve()) or path.stat().st_size > 24 * 1024 * 1024:
            raise ValueError("Invalid motion snapshot path or size")
        body = path.read_bytes()
        if hashlib.sha256(body).hexdigest() != digest:
            raise ValueError("Motion snapshot content hash mismatch")
        bakes[digest] = json.loads(body)
    return bakes


def materialize(rig, event, record, skeleton_hash):
    if record.get("profile") not in {"atlas-motion-1", "atlas-motion-2"} or record["target"]["skeleton_sha256"] != skeleton_hash:
        raise ValueError("Motion snapshot is incompatible with the imported rest skeleton")
    bake = record["bake"]
    captured_travel = (record["profile"] == "atlas-motion-2"
                       and record.get("source", {}).get("family") == "cmu-motionbuilder-bvh"
                       and bake["metrics"].get("root_type") == "root-motion-preserved")
    translation_limit = 12 if captured_travel else 3
    names, pelvis_name, frames = (bake[key] for key in ("bones", "pelvis", "frames"))
    if (bake["fps"] != 30 or not 2 <= len(frames) <= 361 or not 1 <= len(names) <= 53
            or len(set(names)) != len(names) or pelvis_name not in names
            or any(name not in rig.pose.bones for name in names)):
        raise ValueError("Invalid motion sample layout")
    bones = [rig.pose.bones[name] for name in names]
    pelvis = rig.pose.bones[pelvis_name]
    data = rig.animation_data
    action = bpy.data.actions.new(f"ATLAS Motion {event['motion']['id']}")
    data.action = action
    for index, frame in enumerate(frames):
        if (len(frame) != len(bones) + 1 or len(frame[-1]) != 3
                or any(not math.isfinite(value) or abs(value) > translation_limit for value in frame[-1])):
            raise ValueError("Invalid motion translation sample")
        for bone, rotation in zip(bones, frame[:-1]):
            if len(rotation) != 4 or not math.isclose(sum(value * value for value in rotation), 1, abs_tol=.001):
                raise ValueError("Invalid motion quaternion sample")
            bone.rotation_mode = "QUATERNION"
            bone.rotation_quaternion = rotation
            bone.keyframe_insert(data_path="rotation_quaternion", frame=index, group=bone.name)
        pelvis.location = frame[-1]
        pelvis.keyframe_insert(data_path="location", frame=index, group=pelvis.name)
    slot = data.action_slot
    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                for curve in bag.fcurves:
                    for point in curve.keyframe_points:
                        point.interpolation = "LINEAR"
    data.action = None
    for bone in rig.pose.bones:
        bone.matrix_basis.identity()
    return action, slot, 0., float(len(frames) - 1)
