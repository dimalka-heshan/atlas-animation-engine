import math

import pytest

from engine.adapters.blender.retarget_anatomy import arm_direction, refinement_profile


def test_walking_reduces_lateral_reach_and_preserves_forward_and_back_swing():
    profile = refinement_profile("walk", "category")
    forward = arm_direction((.88, -.38, -.27), 1, profile)
    backward = arm_direction((.88, .38, -.27), 1, profile)
    lateral = math.degrees(math.asin(forward[0]))
    assert 9 < lateral < 15
    assert forward[1] < 0 < backward[1] and forward[2] < 0
    assert backward[1] == pytest.approx(-forward[1])
    assert arm_direction((-.88, -.38, -.27), -1, profile) == pytest.approx((-forward[0], forward[1], forward[2]))
    assert math.hypot(*forward) == pytest.approx(1.)


def test_category_limits_are_local_and_expressive_base_is_unrestricted():
    walk = refinement_profile("walk", "category")
    run = refinement_profile("run", "category")
    assert run.elbow_max > walk.elbow_max
    assert refinement_profile("gesture", "category") is None
    assert refinement_profile("walk", "none") is None


def test_elbow_refinement_keeps_a_range_within_each_profile():
    from engine.adapters.blender.retarget_anatomy import elbow_flexion

    profile = refinement_profile("walk", "category")
    values = [elbow_flexion(value, profile) for value in (50, 80, 110)]
    assert profile.elbow_min < values[0] < values[1] < values[2] < profile.elbow_max


def test_overhead_pose_does_not_snap_between_forward_and_back_swing():
    for category in ("idle", "walk", "run", "sit"):
        profile = refinement_profile(category, "category")
        a = arm_direction((.1, -1e-5, .995), 1, profile)
        b = arm_direction((.1, 1e-5, .995), 1, profile)
        assert math.dist(a, b) < .001


def test_bvh_import_rejects_unreviewed_bytes(tmp_path):
    from engine.characters.cmu import reviewed_capture

    path = tmp_path / "35_01.bvh"
    path.write_text("HIERARCHY")
    with pytest.raises(ValueError, match="reviewed CMU"):
        reviewed_capture(path)
