import pytest

from engine.characters.locomotion import compile_movement
from engine.assets.resolution import resolve_project_assets
from engine.core.models import Project


PIN = {"id": "walk", "sha256": "a" * 64}
BAKES = {(PIN["id"], PIN["sha256"]): (PIN, {"category": "walk", "bake": {"metrics": {"calibrated_speed_mps": 1.2}}}, None)}


def actor(name, x, y):
    return {"id": name, "asset": {"id": "human", "version": 1}, "rigged": True, "pivot": "base", "location": [x, y, 0]}


def movement(name, destination=None, **kwargs):
    return {"actor": name, "kind": "walk_to", "motion": PIN, "destination": destination, **kwargs}


def project(entities, actions, *, frames=100, obstacles=None, schema_version="1.5"):
    return Project.model_validate({"schema_version": schema_version, "id": "route", "scene": {"entities": entities},
        "render": {"frames": frames, "fps": 12}, "navigation": {"bounds": [-5, -5, 5, 5], "obstacles": obstacles or []},
        "actions": actions})


def test_walk_builds_exact_arrival_and_editable_overlaid_clips():
    value = project([actor("hero", -2, 0)], [movement("hero", [2, 0, 0], speed_mps=1.2)],
                    obstacles=[[-.5, -.45, .5, .45]])
    compiled, plans = compile_movement(value, BAKES)
    assert not compiled.actions and value.actions
    plan = plans[0]
    assert plan["distance_m"] > 4
    assert plan["points"][-1] == (2, 0)
    hero = compiled.scene.entities[0]
    assert hero.keyframes[-1].location == (2, 0, 0)
    assert hero.clips[0].name == "HumanIdle"
    assert hero.clips[1].overlay and hero.clips[1].blend_out_frames == 4
    assert hero.clips[1].frame_count + hero.clips[1].start_frame == hero.keyframes[-1].frame


def test_approach_stops_at_distance_and_faces_arrived_target():
    value = project([actor("hero", 0, 3), actor("guide", 0, -1)],
                    [movement("hero", kind="approach_actor", target_actor="guide", stop_distance=1)])
    compiled, plans = compile_movement(value, BAKES)
    assert plans[0]["stop_distance_m"] == 1
    assert compiled.scene.entities[0].keyframes[-1].rotation == (0, 0, 0)


def test_approach_finds_reachable_side_when_radial_stop_is_blocked():
    value = project([actor("hero", -3, 0), actor("guide", 1, 0)],
                    [movement("hero", kind="approach_actor", target_actor="guide", stop_distance=1)],
                    obstacles=[[-.25, -.25, .25, .25]])
    _, plans = compile_movement(value, BAKES)
    assert plans[0]["points"][-1] != (0, 0)
    assert plans[0]["stop_distance_m"] == pytest.approx(1)


def test_run_defaults_to_measured_clip_speed():
    value = project([actor("hero", 0, 0)], [movement("hero", [0, -3, 0], kind="run_to")])
    run = {"category": "run", "bake": {"metrics": {"calibrated_speed_mps": 3.2}}}
    _, plans = compile_movement(value, {(PIN["id"], PIN["sha256"]): (PIN, run, None)})
    assert plans[0]["speed_mps"] == 3.
    assert plans[0]["playback"] == pytest.approx(.9375)


def test_delayed_in_range_approach_preserves_authored_idle_heading():
    value = project([actor("hero", 0, 0), actor("guide", .8, 0)],
                    [movement("hero", kind="approach_actor", target_actor="guide", start_frame=10)])
    compiled, _ = compile_movement(value, BAKES)
    hero = compiled.scene.entities[0]
    assert hero.rotation == (0, 0, 0)
    assert [(key.frame, key.rotation[2]) for key in hero.keyframes] == [(7, 0), (10, 90)]
    assert len(hero.clips) == 1


def test_in_range_motion_checks_exact_asset_identity_without_a_strip(tmp_path, monkeypatch):
    value = project([actor("hero", 0, 0)], [movement("hero", [0, 0, 0])])
    compiled, _ = compile_movement(value, BAKES)
    (tmp_path / "assets.sqlite3").touch()
    entry = {"id": "human", "version": 1, "sha256": "asset", "container": {"profile": "human"},
             "inspection": {"report": {"humanoid_mapping": {}, "skeleton_sha256": "rest",
                        "clips": [{"name": "HumanIdle", "duration_seconds": 1}]}}}
    monkeypatch.setattr("engine.assets.resolution.AssetRegistry.resolve", lambda *args: entry)
    key = (PIN["id"], PIN["sha256"])
    record = BAKES[key][1] | {"target": {"id": "human", "version": 2, "sha256": "asset", "skeleton_sha256": "rest"}}
    with pytest.raises(ValueError, match="exact pinned target"):
        resolve_project_assets(compiled, tmp_path, {key: (PIN, record, None)}, movement_actions=value.actions)


def test_routes_reject_crossing_actors_and_out_of_frame_arrivals():
    will_collide = project([actor("one", -2, 0), actor("two", 2, 0)],
                           [movement("one", [2, 0, 0]), movement("two", [-2, 0, 0])])
    with pytest.raises(ValueError, match="violate separation"):
        compile_movement(will_collide, BAKES)
    too_short = project([actor("hero", 0, 0)], [movement("hero", [2, 0, 0])], frames=5)
    with pytest.raises(ValueError, match="does not finish"):
        compile_movement(too_short, BAKES)


def test_schema_14_rejects_new_movement_configuration():
    with pytest.raises(ValueError, match="require schema 1.5"):
        project([actor("hero", 0, 0)], [movement("hero", [1, 0, 0])], schema_version="1.4")


def test_uncycled_human_capture_cannot_drive_guided_locomotion():
    key = (PIN["id"], PIN["sha256"])
    value = project([actor("hero", 0, 0)], [movement("hero", [0, -2, 0])])
    record = BAKES[key][1] | {"source": {"family": "cmu-motionbuilder-bvh"}}
    with pytest.raises(ValueError, match="qualified gait loop"):
        compile_movement(value, {key: (PIN, record, None)})
