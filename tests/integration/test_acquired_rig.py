"""Opt-in acceptance using the actual locally acquired KayKit starter pack."""
import json
import os
from pathlib import Path

import pytest

from engine.assets.registry import AssetRegistry
from engine.core.models import Project
from engine.rendering.pipeline import render_project
from engine.rendering.runtime import capture, find_tool


pytestmark = [pytest.mark.integration, pytest.mark.skipif(os.environ.get("ATLAS_ACQUIRED_INTEGRATION") != "1",
    reason="set ATLAS_ACQUIRED_INTEGRATION=1 after acquiring and inspecting the KayKit starter pack")]


def test_source_rig_slots_skinning_timeline_and_attachment(tmp_path):
    library = Path(os.environ.get("ATLAS_ACQUIRED_LIBRARY", "outputs/v05-library"))
    registry = AssetRegistry(library)
    entry = registry.resolve("kaykit-knight", 1)
    assert entry["inspection"]["report"]["animation_count"] >= 20
    project = Project.model_validate({"schema_version": "1.3", "id": "verify-acquired-rig",
        "render": {"width": 64, "height": 64, "frames": 8, "fps": 4, "samples": 1},
        "scene": {"entities": [
            {"id": "hero", "rigged": True, "asset": {"id": "kaykit-knight", "version": 1},
             "normalize": "unit", "pivot": "base", "location": [0, 0, 0], "equipment": {"right_hand": "prop"},
             "clips": [{"name": "Idle", "start_frame": 1, "frame_count": 2},
                       {"name": "Walking_A", "start_frame": 3, "frame_count": 6, "loop": True}]},
            {"id": "prop", "asset": {"id": "kaykit-crate", "version": 1}, "scale": [.1, .1, .1]},
        ]}})
    video = render_project(project, tmp_path, asset_library=library)
    report = json.loads((video.parent / "manifest.json").read_text())
    assert report["video"]["frames"] == 8
    check = tmp_path / "rig_check.py"
    check.write_text("""import bpy
scene = bpy.context.scene
root = bpy.data.objects['hero']
rig = next(o for o in root.children_recursive if o.type == 'ARMATURE')
skin = next(o for o in root.children_recursive if o.type == 'MESH' and any(m.type == 'ARMATURE' for m in o.modifiers))
assert len(rig.data.bones) >= 20 and len(skin.vertex_groups) > 0
assert any(image.packed_file for image in bpy.data.images)
prop = bpy.data.objects['prop']
assert prop.parent == rig and prop.parent_type == 'BONE' and prop.parent_bone == 'hand.r'
strips = [s for track in rig.animation_data.nla_tracks for s in track.strips]
assert [(s.action.name, s.frame_start, round(s.frame_end)) for s in strips] == [('Idle', 1., 3), ('Walking_A', 3., 9)]
assert all(s.frame_end < round(s.frame_end) for s in strips)
assert abs(strips[1].scale - 4/30) < 1e-6
assert all(s.action_slot for s in strips)
def sample(frame):
    scene.frame_set(frame)
    evaluated = skin.evaluated_get(bpy.context.evaluated_depsgraph_get())
    return tuple(tuple(row) for row in rig.pose.bones['foot.l'].matrix), [tuple(v.co) for v in evaluated.data.vertices], prop.matrix_world.translation.copy()
a, b = sample(4), sample(5)
assert a[0] != b[0]
assert a[1] != b[1]
assert (a[2] - b[2]).length > .001
start = sample(3)[0]
after = sample(9)[0]
rig.animation_data.nla_tracks[-1].mute = True
assert sample(3)[0] != start
assert sample(9)[0] == after
print('RIG_REOPEN_VERIFIED')
""", encoding="utf-8")
    assert "RIG_REOPEN_VERIFIED" in capture([str(find_tool("blender")), "--background", "--disable-autoexec",
        str(video.parent / "scene.blend"), "--python-exit-code", "1", "--python", str(check)], timeout=120)
