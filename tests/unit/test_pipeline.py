import json
import sys
from pathlib import Path

import pytest

from engine.core.models import Project, RenderSettings
from engine.rendering.pipeline import render_project
from engine.rendering.runtime import run_logged
from engine.rendering.video import validate_probe
from engine.storage.jobs import JobStore, atomic_json, contained_path


def probe():
    return {"streams": [{"codec_type": "video", "codec_name": "h264", "width": 320,
        "height": 180, "nb_read_frames": "48", "avg_frame_rate": "24/1",
        "pix_fmt": "yuv420p", "duration": "2.0"}],
        "format": {"duration": "2.0", "format_name": "mov,mp4,m4a,3gp,3g2,mj2"}}


def test_video_contract():
    assert validate_probe(probe(), RenderSettings()) == {"width": 320, "height": 180,
        "frames": 48, "fps": 24.0, "duration": 2.0, "codec": "h264", "pixel_format": "yuv420p"}


@pytest.mark.parametrize("field,value", [("width", 640), ("height", 240),
    ("codec_name", "hevc"), ("nb_read_frames", "47"), ("duration", "1.0"),
    ("avg_frame_rate", "30/1"), ("pix_fmt", "yuv444p"), ("codec_type", "audio")])
def test_bad_video_rejected(field, value):
    data = probe()
    data["streams"][0][field] = value
    with pytest.raises(ValueError):
        validate_probe(data, RenderSettings())


def test_output_boundary_and_atomic_save(tmp_path):
    with pytest.raises(ValueError):
        contained_path(tmp_path, "../outside")
    with pytest.raises(ValueError):
        contained_path(tmp_path, str(tmp_path.parent / "outside"))
    target = contained_path(tmp_path, "manifest.json")
    atomic_json(target, {"state": "running"})
    atomic_json(target, {"state": "succeeded"})
    assert json.loads(target.read_text())["state"] == "succeeded"
    assert list(tmp_path.iterdir()) == [target]


def test_job_persistence(tmp_path):
    store = JobStore(tmp_path / "jobs.sqlite3")
    store.create("job1", "project1", tmp_path / "job1")
    store.update("job1", "failed", "renderer stopped")
    job = JobStore(tmp_path / "jobs.sqlite3").list()[0]
    assert job["status"] == "failed"
    assert job["error"] == "renderer stopped"


def test_process_failure_has_log(tmp_path):
    log = tmp_path / "process.log"
    with pytest.raises(RuntimeError, match="process.log"):
        run_logged([sys.executable, "-c", "print('diagnostic'); raise SystemExit(3)"], log, 10)
    assert "diagnostic" in log.read_text()


def test_process_timeout(tmp_path):
    with pytest.raises(RuntimeError, match="timed out"):
        run_logged([sys.executable, "-c", "import time; time.sleep(60)"], tmp_path / "timeout.log", .1)


def test_failed_render_is_persisted_without_success(tmp_path):
    project = Project.model_validate({"id": "failure", "scene": {"entities": [{"id": "cube"}]}})
    with pytest.raises((ValueError, RuntimeError, FileNotFoundError)):
        render_project(project, tmp_path, blender=tmp_path / "missing-blender.exe")
    jobs = JobStore(tmp_path / "jobs.sqlite3").list()
    assert len(jobs) == 1 and jobs[0]["status"] == "failed"
    manifest = json.loads((Path(jobs[0]["directory"]) / "manifest.json").read_text())
    assert manifest["status"] == "failed"
    assert not (Path(jobs[0]["directory"]) / "video.mp4").exists()


@pytest.mark.parametrize("change", [{"duration": "3.0"}, {"duration": "nan"}, {"format_name": "matroska,webm"}])
def test_invalid_container_rejected(change):
    data = probe()
    data["format"].update(change)
    with pytest.raises(ValueError):
        validate_probe(data, RenderSettings())


def test_unexpected_audio_stream_rejected():
    data = probe()
    data["streams"].append({"codec_type": "audio", "duration": "4.0"})
    with pytest.raises(ValueError):
        validate_probe(data, RenderSettings())


def test_provenance_failure_marks_job_failed(tmp_path, monkeypatch):
    import engine.rendering.pipeline as pipeline

    def fail_digest():
        raise OSError("provenance read denied")

    monkeypatch.setattr(pipeline, "source_digest", fail_digest)
    project = Project.model_validate({"id": "failure", "scene": {}})
    with pytest.raises(OSError, match="provenance"):
        pipeline.render_project(project, tmp_path)
    job = JobStore(tmp_path / "jobs.sqlite3").list()[0]
    assert job["status"] == "failed"
    manifest = json.loads((Path(job["directory"]) / "manifest.json").read_text())
    assert manifest["status"] == "failed"


def test_mutated_project_is_revalidated_before_render(tmp_path):
    from pydantic import ValidationError
    from engine.core.models import Keyframe
    project = Project.model_validate({"id": "mutated", "scene": {"entities": [{"id": "cube"}]}})
    project.scene.entities[0].keyframes.append(Keyframe(frame=49, location=(0, 0, 0)))
    output = tmp_path / "must-not-be-created"
    with pytest.raises(ValidationError, match="frame range"):
        render_project(project, output, blender=tmp_path / "missing.exe")
    assert not output.exists()
