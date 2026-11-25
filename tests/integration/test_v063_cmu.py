import os
from pathlib import Path

import pytest

from engine.characters.motion import load_motion, retarget_cmu


@pytest.mark.integration
@pytest.mark.skipif(os.environ.get("ATLAS_CMU_INTEGRATION") != "1", reason="enable with the reviewed CMU fixture present")
def test_capture_keeps_wave_range_and_canonical_joint_mapping(tmp_path):
    captures = Path(os.environ.get("ATLAS_CMU_LIBRARY", "outputs/v063-cmu"))
    library = Path(os.environ.get("ATLAS_MOTION_TARGET_LIBRARY", "outputs/v052-library"))
    info = retarget_cmu(captures / "141_16.bvh", "mpfb-scholar", "wave", library, tmp_path)
    data, _ = load_motion(tmp_path, info["motion"])
    roles = data["bake"]["anatomical_roles"]
    assert data["settings"]["format"] == "bvh" and data["settings"]["refinement"] == "none"
    assert info["category"] == "gesture" and info["source"]["clip_sha256"] == info["source"]["sha256"]
    assert 60 <= info["frames"] < 100
    assert max(side["lateral_deg"][1] for side in info["metrics"]["arm_angle_ranges"].values()) > 35
    assert info["metrics"]["root_type"] == "root-motion-preserved"
    assert info["metrics"]["source_root_excursion_m"] > .2
    assert roles["target"]["right_middle_3"] == "middle_03_r"
    assert roles["source"]["left_wrist"] == "LeftHand"
    assert "clavicle_l" in data["bake"]["bones"]
    assert retarget_cmu(captures / "141_16.bvh", "mpfb-scholar", "wave", library, tmp_path)["cache_hit"]
