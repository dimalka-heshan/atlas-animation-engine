"""Technical signals verify timing/mixing; these tests do not synthesize speech."""
import json
import math
import os
import struct
import wave

import pytest

from engine.audio.library import AudioLibrary, AudioProvenance
from engine.core.models import Project
from engine.rendering.pipeline import render_project
from engine.rendering.runtime import find_tool
from engine.rendering.runtime import capture
from engine.rendering.video import verify_video

pytestmark = [pytest.mark.integration, pytest.mark.skipif(os.environ.get("ATLAS_INTEGRATION") != "1", reason="set ATLAS_INTEGRATION=1")]


def test_actual_audio_video_export_and_sample_offset(tmp_path):
    source = tmp_path / "signal.wav"
    with wave.open(str(source), "wb") as stream:
        stream.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
        stream.writeframes(b"".join(struct.pack("<h", int(3000 * math.sin(i * .2))) for i in range(6000)))
    meta = AudioProvenance(name="Test signal", creator="ATLAS", source_url="urn:atlas:test:signal",
        license_id="LicenseRef-ATLAS-Generated", license_text="Original technical signal, not speech.",
        approval="approved", render_allowed=True, voice_origin="synthetic")
    library = AudioLibrary(tmp_path / "audio-library")
    library.register(source, "tone", meta)
    project = Project.model_validate({"schema_version": "1.2", "id": "voiced-test",
        "scene": {"entities": [{"id": "cube"}]}, "render": {"width": 32, "height": 32, "frames": 3, "fps": 3, "samples": 1},
        "audio": [{"id": "first", "clip": {"id": "tone", "version": 1}, "start_seconds": .1, "gain": .5},
                  {"id": "second", "clip": {"id": "tone", "version": 1}, "start_seconds": .6, "gain": .5}]})
    video = render_project(project, tmp_path / "renders", audio_library=library.root)
    result = verify_video(video, project.render, find_tool("ffprobe"), expect_audio=True)
    assert result["audio"]["channels"] == 2
    with pytest.raises(ValueError, match="silent"):
        verify_video(video, project.render, find_tool("ffprobe"))
    with wave.open(str(video.parent / "audio-mix.wav"), "rb") as audio:
        assert audio.getnframes() == 48000
        raw = audio.readframes(48000)
    # Delay is measured in samples; no signal exists before the configured start.
    assert not any(raw[:4800 * 4])
    assert any(raw[4900 * 4:10000 * 4])
    assert not any(raw[20000 * 4:28000 * 4])
    assert any(raw[30000 * 4:35000 * 4])
    manifest = json.loads((video.parent / "manifest.json").read_text())
    assert manifest["status"] == "succeeded"
    assert len(manifest["audio"]) == 2
    assert manifest["audio_mix"]["clipped_samples"] == 0
    assert (video.parent / "audio-attributions.txt").is_file()
    check = tmp_path / "check_audio.py"
    check.write_text("import bpy\ns=bpy.context.scene\nassert s.sequence_editor is not None\n"
        "strips=list(s.sequence_editor.strips)\nassert len(strips)==1 and strips[0].type=='SOUND'\n"
        "assert strips[0].frame_start==1\nassert not s.render.use_sequencer\nprint('AUDIO_REOPEN_OK')\n")
    result = capture([str(find_tool("blender")), "--background", "--disable-autoexec", str(video.parent / "scene.blend"),
        "--python-exit-code", "1", "--python", str(check)], timeout=60)
    assert "AUDIO_REOPEN_OK" in result
