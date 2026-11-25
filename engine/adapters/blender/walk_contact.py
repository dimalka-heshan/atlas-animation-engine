"""Apply bounded world-space ankle holds during sampled walking stance."""
from itertools import groupby
from math import dist


MAX_SHIFT_M = .12


def stance_targets(samples):
    keys = {frame: (position, 0.) for frame, position, _ in samples}
    for supporting, segment in groupby(samples, key=lambda sample: sample[2]):
        if not supporting:
            continue
        run = list(segment)
        if len(run) < 3:
            continue
        anchor = run[len(run) // 2][1]
        for index, (frame, point, _) in enumerate(run):
            span = dist(point[:2], anchor[:2])
            factor = min(1., MAX_SHIFT_M / span) if span else 1.
            target = tuple(point[i] + factor * (anchor[i] - point[i]) for i in range(2)) + (point[2],)
            influence = min(1., (index + 1) * .5, (len(run) - index) * .5)
            keys[frame] = target, influence
    return keys


def _positions(rig, feet):
    return [tuple(rig.matrix_world @ foot.head) for foot in feet]


def _sole_z(shoe, groups):
    import bpy

    evaluated = shoe.evaluated_get(bpy.context.evaluated_depsgraph_get())
    vertices = evaluated.data.vertices
    return [min((evaluated.matrix_world @ vertices[index].co).z for index in group) for group in groups]


def stabilize_walk(scene, root, roles, clip):
    from handoff import animate_influence, evaluate, marker

    rig = next(obj for obj in root.children_recursive if obj.type == "ARMATURE")
    shoe = next(obj for obj in root.children_recursive
                if obj.type == "MESH" and "shoes" in obj.get("atlas_source_name", "").casefold())
    sides = ("left", "right")
    feet = [rig.pose.bones[roles[f"{side}_foot"]] for side in sides]
    evaluate(scene, 1)
    shoe_to_root = root.matrix_world.inverted() @ shoe.matrix_world
    groups = [[v.index for v in shoe.data.vertices if sign * (shoe_to_root @ v.co).x > 0] for sign in (1, -1)]
    if not all(groups):
        raise ValueError("Walking correction requires separate MPFB shoe vertex groups")

    start = clip["start_frame"] + clip["blend_frames"]
    stop = clip["start_frame"] + clip["frame_count"] - clip["blend_out_frames"]
    frames = range(start, stop)
    samples = [[], []]
    rotations = [{}, {}]
    before_sole = []
    for frame in frames:
        evaluate(scene, frame)
        heights = _sole_z(shoe, groups)
        before_sole.append(min(heights))
        for i, ankle in enumerate(_positions(rig, feet)):
            samples[i].append((frame, ankle, abs(heights[i]) < .07 and heights[i] <= min(heights) + .025))
            rotation = (rig.matrix_world @ feet[i].matrix).to_quaternion()
            prior = rotations[i].get(frame - 1)
            if prior is not None and prior.dot(rotation) < 0:
                rotation.negate()
            rotations[i][frame] = rotation

    sample_pairs = []
    for side, entries, foot, orientations in zip(sides, samples, feet, rotations):
        targets = stance_targets(entries)
        active = {frame for frame, (_, weight) in targets.items() if weight > 0}
        sample_pairs.append([frame for frame in sorted(active) if frame - 1 in active])
        if not active:
            continue
        target = marker(scene, f"ATLAS {root.name} {side} stance {clip['start_frame']}")
        target.rotation_mode = "QUATERNION"
        shin = rig.pose.bones[roles[f"{side}_shin"]]
        constraint = shin.constraints.new("IK")
        constraint.name = f"ATLAS {side} walking stance {clip['start_frame']}"
        constraint.target = target
        constraint.chain_count = 2
        constraint.use_stretch = False
        constraint.iterations = 64
        for frame, (position, _) in targets.items():
            target.location = position
            target.keyframe_insert(data_path="location", frame=frame)
            target.rotation_quaternion = orientations[frame]
            target.keyframe_insert(data_path="rotation_quaternion", frame=frame)
        influences = [(max(1, start - 1), 0.), *((f, w) for f, (_, w) in targets.items()), (stop, 0.)]
        animate_influence(rig, constraint, influences, "LINEAR")
        orient = foot.constraints.new("COPY_ROTATION")
        orient.name = f"ATLAS {side} stance orientation {clip['start_frame']}"
        orient.target = target
        orient.owner_space = orient.target_space = "WORLD"
        animate_influence(rig, orient, [(frame, float(weight > 0)) for frame, weight in influences], "LINEAR")

    after_positions, after_sole = {}, []
    for frame in frames:
        evaluate(scene, frame)
        after_positions[frame] = _positions(rig, feet)
        after_sole.append(min(_sole_z(shoe, groups)))
    before, after = [], []
    for side, pairs in enumerate(sample_pairs):
        raw = {frame: point for frame, point, _ in samples[side]}
        before.extend(dist(raw[f - 1][:2], raw[f][:2]) for f in pairs)
        after.extend(dist(after_positions[f - 1][side][:2], after_positions[f][side][:2]) for f in pairs)
    fps = scene.render.fps / scene.render.fps_base
    return {"actor": root.name, "clip_start": clip["start_frame"], "contact_pairs": len(before),
            "mean_ankle_drift_before_mps": fps * sum(before) / len(before) if before else None,
            "mean_ankle_drift_after_mps": fps * sum(after) / len(after) if after else None,
            "shoe_min_before_m": min(before_sole, default=None), "shoe_min_after_m": min(after_sole, default=None)}
