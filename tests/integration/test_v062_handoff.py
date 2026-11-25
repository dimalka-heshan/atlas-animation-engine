import json
import os
from pathlib import Path

import pytest

from engine.core.models import Project
from engine.production import ProductionWorkspace, handoff_preview
from engine.rendering.runtime import find_tool, run_logged


pytestmark = [pytest.mark.integration, pytest.mark.skipif(os.environ.get("ATLAS_HANDOFF_INTEGRATION") != "1",
    reason="set ATLAS_HANDOFF_INTEGRATION=1 after preparing the two MPFB actors")]


def test_handoff_world_transform_is_continuous_in_reopened_scene(tmp_path):
    fixture = json.loads(Path("examples/27_v062_fort_handoff.json").read_text(encoding="utf-8"))
    giver, receiver, prop = fixture["scene"]["entities"]
    giver.update(location=[1.06424882, -.84775970, 0], rotation=[0, 0, 53.781])
    receiver.update(location=[1.75, -1.35, 0], rotation=[0, 0, -126.219])
    for actor in (giver, receiver):
        actor["clips"] = [{"name": "HumanIdle", "start_frame": 1, "frame_count": 20, "loop": True}]
    handoff = fixture["handoff"] | {"reach_start": 3, "contact_start": 7, "transfer_frame": 10,
                                    "contact_end": 12, "release_end": 17}
    project = Project.model_validate({"schema_version": "1.6", "id": "handoff-proof",
        "scene": {"entities": [giver, receiver, prop]}, "handoff": handoff,
        "render": {"width": 64, "height": 64, "frames": 20, "fps": 10, "samples": 1, "threads": 4}})
    workspace = ProductionWorkspace(output=tmp_path / "renders",
        asset_library=Path(os.environ.get("ATLAS_MOTION_TARGET_LIBRARY", "outputs/v052-library")))
    result = handoff_preview(project, workspace)
    manifest = json.loads(result.manifest.read_text(encoding="utf-8"))
    assert manifest["video"]["frames"] == 20 and manifest["handoff"]["owners"][-1]["actor"] == "scholar"
    assert result.handoff_report.is_file()
    probe = Path(__file__).with_name("blender_handoff_probe.py").resolve()
    command = [str(find_tool("blender")), "--background", "--factory-startup", "--disable-autoexec",
        "--offline-mode", "--threads", "4", str(result.video.parent / "scene.blend"),
        "--python-exit-code", "1", "--python", str(probe), "--", str(result.video.parent)]
    log = tmp_path / "reopen.log"
    run_logged(command, log, 120)
    assert "ATLAS_HANDOFF_REOPEN_VERIFIED" in log.read_text(encoding="utf-8")
