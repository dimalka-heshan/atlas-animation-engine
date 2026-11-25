"""Measure posed MPFB anatomy in an independently reopened Blender job."""
import argparse
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector


def joints(rig, root, side):
    upper, lower, hand, middle = (rig.pose.bones[name + side] for name in
        ("upperarm_", "lowerarm_", "hand_", "middle_01_"))
    transform = root.matrix_world.inverted() @ rig.matrix_world
    shoulder, elbow, wrist, knuckle = (transform @ bone.head for bone in (upper, lower, hand, middle))
    a, b, c = ((second - first).normalized() for first, second in
               ((shoulder, elbow), (elbow, wrist), (wrist, knuckle)))
    radial = (transform.to_3x3() @ lower.matrix.to_3x3().col[0]).normalized()
    transverse = Vector((1, 0, 0)) if abs(b.x) < .95 else Vector((0, -1, 0))
    reference = (transverse - b * transverse.dot(b)).normalized()
    roll = math.degrees(math.atan2(b.dot(reference.cross(radial)), reference.dot(radial)))
    return {"lateral_deg": math.degrees(math.asin(min(1., abs(a.x)))),
            "elbow_deg": math.degrees(a.angle(b)), "wrist_deg": math.degrees(b.angle(c)),
            "forearm_roll_deg": roll}, [bone.matrix.to_quaternion() for bone in (upper, lower, hand)]


def weighted_sample(root):
    for mesh in root.children_recursive:
        if mesh.type != "MESH" or "hand_l" not in mesh.vertex_groups:
            continue
        group = mesh.vertex_groups["hand_l"].index
        points = [v.index for v in mesh.data.vertices if any(w.group == group and w.weight > .65 for w in v.groups)][:16]
        if points:
            return mesh, points
    raise ValueError("No MPFB hand-weighted vertices found")


def report(scene, root, start, end):
    rig = next(child for child in root.children_recursive if child.type == "ARMATURE")
    samples = {"l": {}, "r": {}}
    mesh, indices = weighted_sample(root)
    prior, shifts, initial = {}, [], []
    peaks = {"l": [0., 0., 0.], "r": [0., 0., 0.]}
    for frame in range(start, end + 1):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        for side in samples:
            record, rotations = joints(rig, root, side)
            samples[side][frame] = record
            if side in prior:
                for i, (old, new) in enumerate(zip(prior[side], rotations)):
                    step = math.degrees(2 * math.acos(min(1., abs(old.dot(new)))))
                    peaks[side][i] = max(peaks[side][i], step)
            prior[side] = rotations
        skinned = mesh.evaluated_get(bpy.context.evaluated_depsgraph_get())
        relative = root.matrix_world.inverted() @ skinned.matrix_world
        points = [relative @ skinned.data.vertices[i].co for i in indices]
        if not initial:
            initial = points
        shifts.extend((new - old).length for old, new in zip(initial, points))
    summary = {side: {field: [min(row[field] for row in frames.values()), max(row[field] for row in frames.values())]
                      for field in frames[start]} for side, frames in samples.items()}
    roll_steps = {side: max((abs((frames[f]["forearm_roll_deg"] - frames[f - 1]["forearm_roll_deg"] + 180) % 360 - 180)
                             for f in range(start + 1, end + 1)), default=0.) for side, frames in samples.items()}
    return {"frames": [start, end], "ranges": summary, "largest_joint_step_deg": peaks,
            "largest_circular_forearm_roll_step_deg": roll_steps,
            "max_evaluated_hand_vertex_displacement_m": max(shifts), "samples": samples}


def render_views(scene, directory, actor, actors, frame):
    scene.frame_set(frame)
    for root in actors:
        if root != actor:
            for obj in root.children_recursive:
                if obj.type == "MESH":
                    obj.hide_render = True
    camera = bpy.data.objects.new("Retarget audit camera", bpy.data.cameras.new("Retarget audit camera"))
    scene.collection.objects.link(camera)
    scene.camera = camera
    scene.render.resolution_x, scene.render.resolution_y = 384, 248
    scene.cycles.samples = 3
    base = actor.matrix_world.translation
    views = {
        "front": ((0, -4.2, 1.1), (0, 0, .86), 46),
        "rear": ((0, 4.2, 1.1), (0, 0, .86), 46),
        "side": ((4.2, 0, 1.1), (0, 0, .86), 46),
        "upper-body": ((1.25, -2.3, 1.24), (0, 0, 1.25), 55),
    }
    for name, (location, target, lens) in views.items():
        camera.location = base + Vector(location)
        camera.rotation_euler = (base + Vector(target) - camera.location).to_track_quat("-Z", "Y").to_euler()
        camera.data.lens = lens
        scene.render.filepath = str(directory / f"{actor.name}-{name}-{frame:04}.png")
        bpy.ops.render.render(write_still=True)
    for root in actors:
        if root != actor:
            for obj in root.children_recursive:
                if obj.type == "MESH":
                    obj.hide_render = False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("job", type=Path)
    parser.add_argument("--stills", type=int)
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    project = json.loads((args.job / "resolved.json").read_text(encoding="utf-8"))
    scene = bpy.context.scene
    roots = [bpy.data.objects[row["id"]] for row in project["scene"]["entities"] if row.get("rigged")]
    end = args.end if args.end is not None else scene.frame_end
    reports = {root.name: report(scene, root, args.start, end) for root in roots}
    (args.job / "retarget-scene-report.json").write_text(json.dumps(reports, indent=2), encoding="utf-8")
    if args.stills is not None:
        directory = args.job / "anatomy-views"
        directory.mkdir(exist_ok=True)
        for actor in roots:
            render_views(scene, directory, actor, roots, args.stills)
    print("ATLAS_RETARGET_SCENE_EVALUATED")


if __name__ == "__main__":
    main()
