import json
import math
import struct
import wave

import pytest

from engine.audio.library import AudioLibrary, AudioProvenance
from engine.core.models import Project


def wav_file(path, seconds=0.25):
    with wave.open(str(path), "wb") as stream:
        stream.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
        stream.writeframes(b"".join(struct.pack("<h", int(2000 * math.sin(i * 0.1))) for i in range(round(seconds * 24000))))
    return path


def rights(**changes):
    return AudioProvenance(name="Original test signal", creator="ATLAS tests", source_url="urn:atlas:test:signal",
        license_id="LicenseRef-ATLAS-Generated", license_text="Original generated test signal; not speech.",
        approval="approved", render_allowed=True, voice_origin="synthetic", **changes)


def test_audio_versions_hashes_and_independent_rights(tmp_path):
    lib = AudioLibrary(tmp_path / "audio")
    source = wav_file(tmp_path / "source.wav")
    first = lib.register(source, "line", rights())
    assert first["version"] == lib.register(source, "line", rights())["version"] == 1
    assert lib.resolve("line", 1)["metadata"]["duration_seconds"] == .25
    changed = rights(); changed.name = "New title"
    assert lib.register(source, "line", changed)["version"] == 2
    assert lib.get("line", 1)["provenance"]["name"] == "Original test signal"
    assert len(list((lib.root / "blobs").glob("*.wav"))) == 1
    lib.resolve("line", 1)["path"].write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="hash|WAV"):
        lib.resolve("line", 1)


def test_recording_requires_owner_and_permission(tmp_path):
    meta = rights(); meta.voice_origin = "recording"
    with pytest.raises(ValueError, match="consent|owner"):
        AudioLibrary(tmp_path / "audio").register(wav_file(tmp_path / "s.wav"), "recording", meta)


def test_measured_audio_overrun_fails_before_render(tmp_path):
    from engine.audio.production import resolve_audio
    lib = AudioLibrary(tmp_path / "audio")
    lib.register(wav_file(tmp_path / "s.wav", 1), "line", rights())
    project = Project.model_validate({"schema_version": "1.2", "id": "overrun", "scene": {},
        "render": {"frames": 24, "fps": 24}, "audio": [{"id": "line", "clip": {"id": "line", "version": 1}, "start_seconds": .2}]})
    with pytest.raises(ValueError, match="beyond video"):
        resolve_audio(project, lib.root)


def test_missing_audio_library_is_not_created(tmp_path):
    from engine.audio.production import resolve_audio
    project = Project.model_validate({"schema_version": "1.2", "id": "missing", "scene": {},
        "audio": [{"id": "line", "clip": {"id": "line", "version": 1}}]})
    root = tmp_path / "missing"
    with pytest.raises(ValueError, match="does not exist"):
        resolve_audio(project, root)
    assert not root.exists()


def test_audio_requires_new_schema_and_valid_events():
    data = {"schema_version": "1.1", "id": "narrated", "scene": {},
            "audio": [{"id": "line", "clip": {"id": "speech", "version": 1}}]}
    with pytest.raises(ValueError, match="1.2"):
        Project.model_validate(data)
    data["schema_version"] = "1.2"
    assert Project.model_validate(data).audio[0].start_seconds == 0
    data["audio"] *= 2
    with pytest.raises(ValueError, match="unique"):
        Project.model_validate(data)


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf")])
def test_invalid_audio_offset_rejected(value):
    with pytest.raises(ValueError):
        Project.model_validate({"schema_version": "1.2", "id": "audio", "scene": {},
            "audio": [{"id": "line", "clip": {"id": "speech", "version": 1}, "start_seconds": value}]})
