"""Independently inspect an ordinary Blender job's editable handoff."""
import json
import math
import sys
from pathlib import Path

import bpy


job = Path(sys.argv[-1])
spec = json.loads((job / "resolved.json").read_text(encoding="utf-8"))
event = spec["handoff"]
scene = bpy.context.scene
prop = bpy.data.objects[event["prop"]]
curves = [c for c in prop.constraints if c.name.startswith("ATLAS ownership")]
assert len(curves) == 2


def sample(frame):
    index = math.floor(frame)
    scene.frame_set(index, subframe=frame - index)
    bpy.context.view_layer.update()
    wrists = [bpy.data.objects[f"ATLAS wrist {event[key]['name']}"] for key in ("giver", "receiver")]
    grips = [bpy.data.objects[f"ATLAS prop grip {event[key]['name']}"] for key in ("grip", "receive_grip")]
    matrix = prop.matrix_world.copy()
    return {"frame": frame, "owner": [c.influence for c in curves], "translation": list(matrix.translation),
            "rotation": list(matrix.to_quaternion()),
            "gap_m": [(grip.matrix_world.translation - wrist.matrix_world.translation).length
                      for grip, wrist in zip(grips, wrists)]}


transfer = event["transfer_frame"]
before, switch, after = [sample(frame) for frame in (transfer - .01, transfer, transfer + .01)]
start, end = sample(1), sample(event["release_end"])
assert start["owner"] == before["owner"] == [1., 0.]
assert switch["owner"] == after["owner"] == end["owner"] == [0., 1.]
contacts = [sample(frame) for frame in range(event["contact_start"], event["contact_end"] + 1)]
error = max(max(row["gap_m"]) for row in [before, *contacts, after])
switch_delta = math.dist(before["translation"], switch["translation"])
rotation_delta = math.dist(before["rotation"], switch["rotation"])
assert error < .012 and switch_delta < .003 and rotation_delta < 1e-5
assert start["gap_m"][0] < .001 and end["gap_m"][1] < .001
speech = None
if spec["performances"]:
    sample(transfer)
    actor = bpy.data.objects[event["giver"]["actor"]]
    face = next(mesh for mesh in actor.children_recursive if mesh.type == "MESH" and mesh.data.shape_keys
                and "jawOpen" in mesh.data.shape_keys.key_blocks)
    values = []
    for frame in range(event["contact_start"], event["contact_end"] + 1):
        sample(frame)
        keys = face.data.shape_keys.key_blocks
        values.append(max(key.value for key in keys if key.name.startswith("viseme_")))
    speech = max(values)
    assert speech > .25
(job / "reopened-handoff.json").write_text(json.dumps({"samples": [start, before, switch, after, end],
    "max_contact_error_m": error, "switch_displacement_m": switch_delta,
    "switch_quaternion_delta": rotation_delta, "peak_viseme_during_contact": speech}, indent=2), encoding="utf-8")
print("ATLAS_HANDOFF_REOPEN_VERIFIED")
