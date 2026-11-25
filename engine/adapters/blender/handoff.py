"""Build an editable, measured two-arm prop handoff in a Blender scene."""
import math

import bpy
from mathutils import Vector


CONTACT_TOLERANCE_M = .012
SWITCH_TOLERANCE_M = .003


def marker(scene, name, location=(0, 0, 0), parent=None):
    obj = bpy.data.objects.new(name, None)
    scene.collection.objects.link(obj)
    obj.empty_display_size = .04
    obj.parent = parent
    obj.location = location
    return obj


def copy_location(owner, name, target, bone=""):
    constraint = owner.constraints.new("COPY_LOCATION")
    constraint.name = name
    constraint.target = target
    constraint.subtarget = bone
    constraint.owner_space = constraint.target_space = "WORLD"
    return constraint


def animate_influence(owner, constraint, points, interpolation):
    for frame, value in points:
        constraint.influence = value
        constraint.keyframe_insert(data_path="influence", frame=frame)
    data = owner.animation_data
    path = constraint.path_from_id("influence")
    for layer in data.action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                for curve in bag.fcurves:
                    if curve.data_path == path:
                        for point in curve.keyframe_points:
                            point.interpolation = interpolation


def contact_arm(scene, actor, roles, anchor, target, event):
    rig = next(obj for obj in actor.children_recursive if obj.type == "ARMATURE")
    hand = anchor["hand"]
    forearm = rig.pose.bones[roles[f"{hand}_forearm"]]
    wrist_name = roles[f"{hand}_hand"]
    grip = marker(scene, f"ATLAS wrist {anchor['name']}")
    copy_location(grip, "Follow wrist origin", rig, wrist_name)

    constraint = forearm.constraints.new("IK")
    constraint.name = f"ATLAS reach {anchor['name']}"
    constraint.target = target
    constraint.chain_count = 2
    constraint.use_stretch = False
    constraint.iterations = 128
    animate_influence(rig, constraint, [(event["reach_start"], 0.), (event["contact_start"], 1.),
        (event["contact_end"], 1.), (event["release_end"], 0.)], "LINEAR")
    return grip


def evaluate(scene, frame):
    index = math.floor(frame)
    scene.frame_set(index, subframe=frame - index)
    bpy.context.view_layer.update()


def build_handoff(scene, entities, mappings, event):
    prop = entities[event["prop"]]
    bpy.context.view_layer.update()
    basis = prop.matrix_world.to_3x3()
    contact = Vector(event["contact"])
    grips, wrists, carriers = [], [], []
    for key, grip_key in (("giver", "grip"), ("receiver", "receive_grip")):
        definition, anchor = event[key], event[grip_key]
        offset = basis @ Vector(anchor["offset"])
        if offset.length > .4 + 1e-6:
            raise ValueError("Prop grip offset exceeds 0.4 meters from the object origin")
        target = marker(scene, f"ATLAS target {definition['name']}", contact + offset)
        wrist = contact_arm(scene, entities[definition["actor"]], mappings[definition["actor"]], definition, target, event)
        grip = marker(scene, f"ATLAS prop grip {anchor['name']}", anchor["offset"], prop)
        carrier = marker(scene, f"ATLAS prop origin from {definition['name']}", -offset, wrist)
        grips.append(grip)
        wrists.append(wrist)
        carriers.append(carrier)

    transfer = event["transfer_frame"]
    for carrier, owner, weights in zip(carriers, (event["giver"], event["receiver"]), ((1., 0.), (0., 1.))):
        constraint = copy_location(prop, f"ATLAS ownership {owner['actor']}", carrier)
        animate_influence(prop, constraint, [(1, weights[0]), (transfer, weights[1])], "CONSTANT")

    distances = [0., 0.]
    samples = []
    contact_frames = range(event["contact_start"], event["contact_end"] + 1)
    sample_times = sorted({*contact_frames, transfer - .01, transfer + .01})
    for frame in sample_times:
        evaluate(scene, frame)
        errors = [(grip.matrix_world.translation - wrist.matrix_world.translation).length
                  for grip, wrist in zip(grips, wrists)]
        distances = [max(a, b) for a, b in zip(distances, errors)]
        if transfer - .011 < frame < transfer + .011:
            samples.append({"frame": frame, "prop_world": list(prop.matrix_world.translation), "wrist_error_m": errors})
    jump = (Vector(samples[0]["prop_world"]) - Vector(samples[1]["prop_world"])).length
    if max(distances) > CONTACT_TOLERANCE_M or jump > SWITCH_TOLERANCE_M:
        raise ValueError(f"Handoff reach or ownership continuity failed for {prop.name}: wrist errors {distances}, switch {jump:.5f} m")
    evaluate(scene, event["release_end"])
    retained_error = (grips[1].matrix_world.translation - wrists[1].matrix_world.translation).length
    if retained_error > CONTACT_TOLERANCE_M:
        raise ValueError("Receiver did not retain the prop through release")
    return {"prop": event["prop"], "owners": [{"frame": 1, "actor": event["initial_owner"]},
            {"frame": transfer, "actor": event["receiver"]["actor"]}], "contact_frames": list(contact_frames),
            "wrist_error_m": distances, "switch_displacement_m": jump, "release_error_m": retained_error,
            "switch_samples": samples, "tolerance_m": {"wrist": CONTACT_TOLERANCE_M, "switch": SWITCH_TOLERANCE_M}}
