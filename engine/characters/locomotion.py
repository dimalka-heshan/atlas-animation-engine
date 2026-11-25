"""Compile bounded flat-ground movement to existing ATLAS transform and NLA tracks."""
from bisect import bisect_right
from itertools import combinations
from math import atan2, ceil, degrees, dist

from engine.characters.navigation import plan_approach, plan_route, segments_conflict
from engine.core.models import Project, RiggedEntity


def _sample(points, frames, frame):
    index = bisect_right(frames, frame)
    if not index:
        return points[0]
    if index == len(frames):
        return points[-1]
    a, b = frames[index - 1:index + 1]
    fraction = (frame - a) / (b - a)
    return tuple(x + (y - x) * fraction for x, y in zip(points[index - 1], points[index]))


def _heading(source, target, previous):
    if source == target:
        return previous
    yaw = degrees(atan2(target[0] - source[0], source[1] - target[1]))
    return previous + (yaw - previous + 180) % 360 - 180


def _transform_keys(points, frames, initial, facing):
    yaw = initial
    keys = []
    for i, (frame, point) in enumerate(zip(frames, points)):
        next_point = points[i + 1] if i + 1 < len(points) else facing
        if next_point is not None:
            next_yaw = _heading(point, next_point, yaw)
            if abs(next_yaw - yaw) > 1e-4 and (
                    (i == 0 and frame > 1) or (i > 0 and frame - frames[i - 1] > 3)):
                lead = max(1, frame - 3)
                x, y = _sample(points, frames, lead)
                keys.append({"frame": lead, "location": [x, y, 0], "rotation": [0, 0, yaw]})
            yaw = next_yaw
        keys.append({"frame": frame, "location": [*point, 0], "rotation": [0, 0, yaw]})
    return keys


def compile_movement(project, motions):
    if not project.actions:
        return project, []
    if not project.scene.environment.ground:
        raise ValueError("Flat movement requires a ground plane")
    nav, fps = project.navigation, project.render.fps
    actors = {entity.id: entity for entity in project.scene.entities if isinstance(entity, RiggedEntity)}
    actions = {action.actor: action for action in project.actions}
    if len(actors) > 64 or any(actor.keyframes for actor in actors.values()):
        raise ValueError("Deterministic separation supports up to 64 actors without manual transform keys")
    paths, pending = {}, set()

    def route(identifier):
        if identifier in paths:
            return paths[identifier]
        if identifier in pending:
            raise ValueError("Mutually dependent approach actions are unsupported")
        actor = actors[identifier]
        start = actor.location[:2]
        action = actions.get(identifier)
        if action is None:
            return {"points": [start], "frames": [1]}
        if abs(actor.location[2]) > 1e-7 or any(abs(v) > 1e-7 for v in actor.rotation[:2]):
            raise ValueError("Movement actors must be upright on the Z=0 navigation plane")
        pending.add(identifier)
        facing = None
        if action.target_actor:
            target = route(action.target_actor)
            if target["frames"][-1] > action.start_frame:
                raise ValueError("Approach the target after it arrives")
            if abs(actors[action.target_actor].location[2]) > 1e-7 or action.stop_distance <= nav.actor_separation:
                raise ValueError("Approach requires the same ground plane and a stop distance greater than actor separation")
            facing = target["points"][-1]
            points = plan_approach(start, facing, action.stop_distance, nav.bounds, nav.obstacles,
                                   nav.clearance, nav.actor_separation)
        else:
            targets = action.waypoints or [action.destination]
            if any(abs(target[2]) > 1e-7 for target in targets):
                raise ValueError("Navigation only supports destinations on the Z=0 ground plane")
            points = [start]
            for target in targets:
                points.extend(plan_route(points[-1], target[:2], nav.bounds, nav.obstacles, nav.clearance)[1:])
        if len(points) > 256:
            raise ValueError("Movement route exceeds 256 path knots")
        record = motions[action.motion.id, action.motion.sha256][1]
        speed = record["bake"]["metrics"].get("calibrated_speed_mps")
        expected = "run" if action.kind == "run_to" else "walk"
        if record["category"] != expected or not speed or not .25 <= speed <= 8:
            raise ValueError(f"Action {action.kind} requires a measured {expected} motion")
        requested_speed = action.speed_mps if action.speed_mps is not None else speed
        frames = [action.start_frame]
        length = 0.
        for a, b in zip(points, points[1:]):
            length += dist(a, b)
            frame = action.start_frame + ceil(length * fps / requested_speed - 1e-9)
            frames.append(max(frames[-1] + 1, frame))
        if frames[-1] > project.render.frames:
            raise ValueError(f"Movement for {identifier} does not finish before the last rendered frame")
        duration = (frames[-1] - frames[0]) / fps
        speed_actual = length / duration if duration else 0
        playback = speed_actual / speed if duration else 1
        if not .5 <= playback <= 2:
            raise ValueError(f"Requested speed is outside the calibrated range for {action.motion.id}")
        report = {"actor": identifier, "kind": action.kind, "motion": action.motion.model_dump(), "points": points,
                  "frames": frames, "distance_m": length, "speed_mps": speed_actual, "playback": playback,
                  "facing": facing, "stop_distance_m": dist(points[-1], facing) if facing else None}
        paths[identifier] = report
        pending.remove(identifier)
        return report

    for identifier in actions:
        route(identifier)
    for a, b in combinations(actors, 2):
        if a not in actions and b not in actions:
            continue
        p, q = route(a), route(b)
        times = sorted({1, project.render.frames, *p["frames"], *q["frames"]})
        for start, end in zip(times, times[1:]):
            p1, p2 = (_sample(p["points"], p["frames"], f) for f in (start, end))
            q1, q2 = (_sample(q["points"], q["frames"], f) for f in (start, end))
            if segments_conflict(p1, p2, q1, q2, nav.actor_separation):
                raise ValueError(f"Actor paths {a} and {b} violate separation during frames {start}–{end}")

    effective = project.model_dump(mode="json")
    effective["actions"] = []
    for actor in effective["scene"]["entities"]:
        identifier = actor["id"]
        if identifier not in paths:
            continue
        plan = paths[identifier]
        first, last = plan["frames"][0], plan["frames"][-1]
        count = last - first
        blend = min(actions[identifier].blend_frames, max(0, (count - 1) // 2))
        actor["keyframes"] = _transform_keys(plan["points"], plan["frames"], actor["rotation"][2], plan["facing"])
        actor["interpolation"] = "LINEAR"
        actor["clips"] = [{"name": "HumanIdle", "start_frame": 1, "frame_count": project.render.frames, "loop": True}]
        if count:
            pin = plan["motion"]
            actor["clips"].append({"name": pin["id"], "motion": pin, "start_frame": first, "frame_count": count,
                "loop": True, "speed": plan["playback"], "blend_frames": blend, "blend_out_frames": blend,
                "overlay": True, "foot_lock": actions[identifier].foot_lock})
    return Project.model_validate(effective), [paths[id] for id in sorted(paths)]
