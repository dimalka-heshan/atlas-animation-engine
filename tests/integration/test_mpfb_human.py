"""Opt-in test using the real, pinned MPFB runtime installed by ATLAS."""
import os
from pathlib import Path

import pytest

from engine.characters.mpfb import HumanSpec, generate
from engine.rendering.runtime import find_tool, run_logged


pytestmark = [pytest.mark.integration, pytest.mark.skipif(os.environ.get("ATLAS_MPFB_INTEGRATION") != "1",
    reason="set ATLAS_MPFB_INTEGRATION=1 after installing the pinned MPFB runtime")]


def test_mpfb_character_keeps_facial_and_skeletal_animation_after_reopening(tmp_path):
    runtime = Path(os.environ.get("ATLAS_MPFB_RUNTIME", "outputs/v051-mpfb"))
    spec_path = Path(__file__).resolve().parents[2] / "examples/humans/curator.json"
    spec = HumanSpec.model_validate_json(spec_path.read_text(encoding="utf-8"))
    entry = generate(spec, runtime, tmp_path / "library")
    report = entry["inspection"]
    assert report["skeleton_count"] == 1 and report["skinned_mesh_count"] == 9
    assert len(report["skeleton"]) == 53 and report["humanoid_mapping"]["head"] == "head"
    assert report["missing_textures"] == [] and len(report["facial_shape_keys"]) == 12
    assert [clip["name"] for clip in report["clips"]] == ["HumanIdle", "HumanPresent"]
    adapters = Path(__file__).resolve().parents[2] / "engine/adapters/blender"
    check = tmp_path / "verify.py"
    check.write_text(f'''import sys
import bpy
sys.path.insert(0, {str(adapters)!r})
from asset_import import import_asset
from facial import apply_performance

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
root, _ = import_asset({entry['artifact']!r}, "speaker", pivot="base", profile="human", fps=24,
    clips=[{{"name":"HumanPresent", "start_frame":1, "frame_count":60, "speed":1, "loop":False, "blend_frames":0}}])
apply_performance(root, {{"profile":"mpfb-visemes-1", "start_seconds":.25, "smoothing_seconds":.04,
    "blink_frames":[24], "timeline":{{"duration_seconds":1.5,"cues":[
        {{"start":0,"end":.65,"value":"D"}}, {{"start":.65,"end":1.5,"value":"X"}}]}}}}, 24)
bpy.ops.wm.save_as_mainfile(filepath={str(tmp_path / 'speaker.blend')!r})
bpy.ops.wm.open_mainfile(filepath={str(tmp_path / 'speaker.blend')!r})
scene = bpy.context.scene
root = bpy.data.objects['speaker']
rig = next(obj for obj in root.children_recursive if obj.type=='ARMATURE')
face = next(obj for obj in root.children_recursive if obj.type=='MESH' and obj.data.shape_keys
            and 'jawOpen' in obj.data.shape_keys.key_blocks and len(obj.data.shape_keys.key_blocks)==13)
keys = face.data.shape_keys.key_blocks
scene.frame_set(1)
initial = rig.pose.bones['head'].matrix.copy()
assert keys['viseme_aa'].value < 1e-6
scene.frame_set(14)
assert keys['viseme_aa'].value > .8 and keys['jawOpen'].value > .18
assert initial != rig.pose.bones['head'].matrix
scene.frame_set(24)
assert keys['eyeBlinkLeft'].value > .9 and keys['eyeBlinkRight'].value > .9
scene.frame_set(46)
assert all(abs(key.value) < 1e-6 for key in keys[1:])
assert all(strip.action_slot for track in rig.animation_data.nla_tracks for strip in track.strips)
print('MPFB_REOPEN_VERIFIED')
''', encoding="utf-8")
    log = tmp_path / "verification.log"
    run_logged([str(find_tool("blender")), "--background", "--factory-startup", "--disable-autoexec",
                "--threads", "4", "--python-exit-code", "1", "--python", str(check)], log, 120)
    assert "MPFB_REOPEN_VERIFIED" in log.read_text(encoding="utf-8")
