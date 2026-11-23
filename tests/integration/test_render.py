"""Real external processes. Opt in with ATLAS_INTEGRATION=1."""
import json
import os
from pathlib import Path

import pytest

from engine.core.models import Project
from engine.rendering.pipeline import render_project
from engine.rendering.runtime import capture, find_tool
from engine.rendering.video import verify_video

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(os.environ.get("ATLAS_INTEGRATION") != "1", reason="set ATLAS_INTEGRATION=1")]


@pytest.mark.parametrize("render_engine", ["cycles", "eevee"])
def test_real_animation_pipeline(tmp_path, render_engine):
    project = Project.model_validate({"id": "smoke", "render": {"width": 64, "height": 64,
        "frames": 3, "fps": 3, "samples": 4, "engine": render_engine}, "scene": {
        "entities": [{"id": "ball", "primitive": "uv_sphere", "location": [-1, 0, 1],
                      "keyframes": [{"frame": 1, "location": [-1, 0, 1]},
                                    {"frame": 3, "location": [1, 0, 1]}]}],
        "camera": {"target_entity": "ball"}}})
    video = render_project(project, tmp_path)
    result = verify_video(video, project.render, find_tool("ffprobe"))
    assert result["duration"] == 1.0
    assert result["frames"] == 3
    manifest = json.loads((video.parent / "manifest.json").read_text())
    assert manifest["status"] == "succeeded"
    assert (video.parent / "scene.blend").stat().st_size > 1000
    # Reopen saved scene and independently evaluate the animation at its midpoint.
    inspector = tmp_path / "inspect_scene.py"
    inspector.write_text("""import bpy, json
s = bpy.context.scene
s.frame_set(2)
ball = bpy.data.objects['ball']
assert abs(ball.location.x) < 0.0001, ball.location[:]
assert s.camera.constraints[0].target == ball
print('INSPECTION_OK')
""")
    result = capture([str(find_tool("blender")), "--background", "--disable-autoexec",
                      str(video.parent / "scene.blend"), "--python-exit-code", "1",
                      "--python", str(inspector)], timeout=120)
    assert "INSPECTION_OK" in result
    first = (video.parent / "frames" / "000001.png").read_bytes()
    last = (video.parent / "frames" / "000003.png").read_bytes()
    assert first != last


def test_final_manifest_failure_cannot_report_success(tmp_path, monkeypatch):
    import engine.rendering.pipeline as pipeline

    original = pipeline.atomic_json

    def fail_success_manifest(path, data):
        if path.name == "manifest.json" and data.get("status") == "succeeded":
            raise OSError("final manifest write denied")
        return original(path, data)

    monkeypatch.setattr(pipeline, "atomic_json", fail_success_manifest)
    project = Project.model_validate({"id": "finalize-failure", "scene": {"entities": [{"id": "cube"}]},
                                     "render": {"width": 32, "height": 32, "frames": 1, "samples": 1}})
    with pytest.raises(OSError, match="final manifest"):
        pipeline.render_project(project, tmp_path)
    from engine.storage.jobs import JobStore
    job = JobStore(tmp_path / "jobs.sqlite3").list()[0]
    assert job["status"] == "failed"
    manifest = json.loads((Path(job["directory"]) / "manifest.json").read_text())
    assert manifest["status"] == "failed"


def test_primitive_library_and_transform_channels(tmp_path):
    kinds = ["cube", "uv_sphere", "ico_sphere", "cylinder", "cone", "torus", "plane"]
    project = Project.model_validate({"id": "primitives", "render": {"width": 64, "height": 64,
        "frames": 3, "samples": 2}, "scene": {
        "entities": [{"id": kind, "primitive": kind, "location": [i * 3, 0, 1]} for i, kind in enumerate(kinds)],
        "camera": {"location": [9, -24, 20], "target": [9, 0, 1], "depth_of_field": True,
                   "keyframes": [{"frame": 1, "location": [9, -24, 20]}, {"frame": 3, "location": [11, -24, 20]}]},
        "lights": [{"id": "sun", "kind": "SUN", "energy": 2}, {"id": "fill", "kind": "POINT"}]}})
    from engine.core.models import Keyframe
    project.scene.entities[0].keyframes = [Keyframe(frame=1, rotation=(0, 0, 0), scale=(1, 1, 1)),
                                          Keyframe(frame=3, rotation=(0, 0, 90), scale=(2, 2, 2))]
    video = render_project(project, tmp_path)
    inspector = tmp_path / "inspect_primitives.py"
    inspector.write_text("""import bpy, math
s = bpy.context.scene
s.frame_set(2)
cube = bpy.data.objects['cube']
assert abs(cube.rotation_euler.z - math.pi/4) < 0.0001
assert abs(cube.scale.x - 1.5) < 0.0001
assert abs(s.camera.location.x - 10) < 0.0001
assert s.camera.data.dof.use_dof
for name in ['cube','uv_sphere','ico_sphere','cylinder','cone','torus','plane']:
    assert bpy.data.objects[name].type == 'MESH'
    assert len(bpy.data.objects[name].data.polygons) > 0
print('LIBRARY_OK')
""")
    result = capture([str(find_tool("blender")), "--background", "--disable-autoexec",
                      str(video.parent / "scene.blend"), "--python-exit-code", "1",
                      "--python", str(inspector)], timeout=120)
    assert "LIBRARY_OK" in result
