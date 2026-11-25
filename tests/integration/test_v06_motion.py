"""Execute a licensed walk bake and reopen the resulting production blend."""
import json
import os
from pathlib import Path

import pytest

from engine.characters.motion import retarget
from engine.core.models import Project
from engine.rendering.pipeline import render_project
from engine.rendering.runtime import find_tool, run_logged


pytestmark = [pytest.mark.integration, pytest.mark.skipif(os.environ.get("ATLAS_MOTION_INTEGRATION") != "1",
    reason="set ATLAS_MOTION_INTEGRATION=1 after preparing the KayKit and MPFB libraries")]


def test_licensed_walk_bake_routes_and_reopens(tmp_path):
    source = Path(os.environ.get("ATLAS_MOTION_SOURCE_LIBRARY", "outputs/v05-library"))
    library = Path(os.environ.get("ATLAS_MOTION_TARGET_LIBRARY", "outputs/v052-library"))
    cache = tmp_path / "motions"
    args = ("kaykit-knight", "Walking_A", "mpfb-curator", "walk", source, library, cache)
    motion = retarget(*args)
    assert not motion["cache_hit"] and retarget(*args)["cache_hit"]
    assert motion["metrics"]["root_type"] == "in-place"
    assert max(map(abs, motion["metrics"]["post_ground_z_range_m"])) < 1e-4
    project = Project.model_validate({"schema_version": "1.5", "id": "motion-proof",
        "render": {"width": 64, "height": 64, "samples": 1, "frames": 14, "fps": 10},
        "scene": {"entities": [{"id": "hero", "asset": {"id": "mpfb-curator", "version": 1},
            "rigged": True, "pivot": "base", "location": [0, 0, 0]}]}, "navigation": {"bounds": [-3, -3, 3, 3]},
        "actions": [{"actor": "hero", "kind": "walk_to", "motion": motion["motion"], "destination": [0, -.9, 0],
                     "speed_mps": 1.2, "start_frame": 2, "blend_frames": 1}]})
    video = render_project(project, tmp_path / "renders", asset_library=library, motion_cache=cache)
    manifest = json.loads((video.parent / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["video"]["frames"] == 14
    assert manifest["motions"][0]["source"]["clip"] == "Walking_A"
    check = tmp_path / "reopen.py"
    check.write_text('''import bpy
from mathutils import Vector
scene = bpy.context.scene
actor = bpy.data.objects['hero']
rig = next(o for o in actor.children_recursive if o.type == 'ARMATURE')
assert len([o for o in bpy.data.objects if o.type == 'ARMATURE']) == 1
tracks = [list(track.strips)[0] for track in rig.animation_data.nla_tracks]
assert tracks[1].action.name.startswith('ATLAS Motion walk') and tracks[1].action_slot
assert tracks[1].blend_in == tracks[1].blend_out == 1
scene.frame_set(1)
assert actor.location.length < 1e-6
scene.frame_set(4)
first = rig.pose.bones['calf_l'].matrix.copy()
scene.frame_set(7)
assert first != rig.pose.bones['calf_l'].matrix
scene.frame_set(14)
assert (actor.location - Vector((0, -.9, 0))).length < 1e-6
print('ATLAS_MOVEMENT_VERIFIED')
''', encoding="utf-8")
    log = tmp_path / "reopen.log"
    run_logged([str(find_tool("blender")), "--background", "--factory-startup", "--disable-autoexec", "--offline-mode",
        "--threads", "4", str(video.parent / "scene.blend"), "--python-exit-code", "1", "--python", str(check)], log, 120)
    assert "ATLAS_MOVEMENT_VERIFIED" in log.read_text(encoding="utf-8")
