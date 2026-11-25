import os
from pathlib import Path

import pytest

from engine.characters.motion import load_motion, retarget_cmu
from engine.core.models import Project
from engine.production import ProductionWorkspace, preview


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


@pytest.mark.integration
@pytest.mark.skipif(os.environ.get("ATLAS_CMU_INTEGRATION") != "1", reason="enable with the reviewed CMU fixture present")
def test_preserved_capture_can_materialize_a_run_longer_than_three_meters(tmp_path):
    captures = Path(os.environ.get("ATLAS_CMU_LIBRARY", "outputs/v063-cmu"))
    library = Path(os.environ.get("ATLAS_MOTION_TARGET_LIBRARY", "outputs/v052-library"))
    cache = tmp_path / "motions"
    info = retarget_cmu(captures / "141_34.bvh", "mpfb-scholar", "run", library, cache)
    assert info["metrics"]["source_root_excursion_m"] > 4
    project = Project.model_validate({"schema_version": "1.6", "id": "captured-travel",
        "scene": {"entities": [{"id": "runner", "asset": {"id": "mpfb-scholar", "version": 1},
            "rigged": True, "pivot": "base", "location": [0, 0, 0], "clips": [{"name": "run",
                "motion": info["motion"], "start_frame": 1, "frame_count": 4}]}]},
        "render": {"width": 64, "height": 64, "frames": 4, "fps": 24, "samples": 1, "threads": 4}})
    result = preview(project, ProductionWorkspace(output=tmp_path / "renders", asset_library=library, motion_cache=cache))
    assert result.video.is_file()
