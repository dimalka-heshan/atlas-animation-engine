"""Real Blender save/reopen, shape-key evaluation and generic jaw mapping."""
import os
from pathlib import Path
import subprocess

import pytest

from engine.rendering.runtime import find_tool

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(os.environ.get('ATLAS_INTEGRATION') != '1', reason='set ATLAS_INTEGRATION=1')]


def test_facial_animation_survives_reopen_and_rests(tmp_path):
    module_dir = Path(__file__).resolve().parents[2] / 'engine/adapters/blender'
    script = tmp_path / 'face_test.py'
    scene = tmp_path / 'face.blend'
    script.write_text(f'''
import sys, math
sys.path.insert(0, {str(module_dir)!r})
import bpy
import facial
assert hasattr(facial, 'build_talking_head'), 'Talking head builder missing'
bpy.ops.wm.read_factory_settings(use_empty=True)
root = facial.build_talking_head({{'id': 'hero'}})
timeline = {{'duration_seconds': 1, 'cues': [{{'start': 0, 'end': .5, 'value': 'D'}}, {{'start': .5, 'end': 1, 'value': 'X'}}]}}
spec = {{'timeline': timeline, 'start_seconds': .25, 'profile': 'atlas-face-1'}}
facial.apply_performance(root, spec, 24)
mouth = next(o for o in root.children_recursive if o.get('atlas_mouth'))
mouth_name = mouth.name
bpy.context.scene.frame_set(12)
assert mouth.data.shape_keys.key_blocks['D'].value > .9
bpy.context.scene.frame_set(31)
assert all(abs(k.value) < 1e-6 for k in mouth.data.shape_keys.key_blocks[1:])
bpy.ops.wm.save_as_mainfile(filepath={str(scene)!r})
bpy.ops.wm.open_mainfile(filepath={str(scene)!r})
mouth = bpy.data.objects[mouth_name]
bpy.context.scene.frame_set(12)
assert mouth.data.shape_keys.key_blocks['D'].value > .9
bpy.context.scene.frame_set(31)
assert all(abs(k.value) < 1e-6 for k in mouth.data.shape_keys.key_blocks[1:])
root = bpy.data.objects['hero']
try:
    facial.apply_performance(root, {{**spec, 'controls': {{'kind': 'shape_keys', 'object': mouth.name, 'mapping': dict.fromkeys('ABCDEFGH', 'absent')}}}}, 24)
    raise AssertionError('Missing shape key accepted')
except ValueError:
    pass
bpy.ops.object.armature_add()
rig = bpy.context.object
rig.name = 'rig'
rig.parent = root
controls = {{'kind': 'jaw_bone', 'object': 'rig', 'bone': 'Bone', 'axis': 'X', 'angles': {{c: (.3 if c == 'D' else 0) for c in 'ABCDEFGHX'}}}}
facial.apply_performance(root, {{**spec, 'controls': controls}}, 24)
bpy.context.scene.frame_set(12)
assert abs(rig.pose.bones['Bone'].rotation_euler.x - .3) < 1e-5
bpy.context.scene.frame_set(31)
assert abs(rig.pose.bones['Bone'].rotation_euler.x) < 1e-5
print('ATLAS_FACIAL_VERIFIED')
''', encoding='utf-8')
    result = subprocess.run([str(find_tool('blender')), '--background', '--python-exit-code', '1', '--python', str(script)], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'ATLAS_FACIAL_VERIFIED' in result.stdout
