import pytest

from engine.core.models import Project


def data():
    return {"schema_version": "1.2", "id": "talking", "scene": {"entities": [{"id": "host", "character": "atlas-face-1"}]},
        "audio": [{"id": "line", "clip": {"id": "speech", "version": 1}, "role": "dialogue", "speaker": "host"}],
        "performances": [{"actor_id": "host", "audio_event_id": "line", "timeline": {
            "audio_sha256": "a" * 64, "duration_seconds": 1, "version": "1.14.0", "cues": [{"start": 0, "end": 1, "value": "D"}]}}]}


def test_character_and_lipsync_require_12():
    assert Project.model_validate(data()).performances[0].actor_id == "host"
    spec = data(); spec["schema_version"] = "1.1"
    with pytest.raises(ValueError, match="1.2"):
        Project.model_validate(spec)


@pytest.mark.parametrize("change", ["actor", "audio", "speaker", "static", "duplicate"])
def test_invalid_performance_assignment_rejected(change):
    spec = data()
    if change == "actor": spec["performances"][0]["actor_id"] = "missing"
    if change == "audio": spec["performances"][0]["audio_event_id"] = "missing"
    if change == "speaker": spec["audio"][0]["speaker"] = "another"
    if change == "static": spec["scene"]["entities"] = [{"id": "host", "primitive": "cube"}]
    if change == "duplicate": spec["performances"] *= 2
    with pytest.raises(ValueError):
        Project.model_validate(spec)


def test_lipsync_audio_hash_must_match_resolved_clip(tmp_path):
    from engine.audio.library import AudioLibrary
    from engine.audio.production import resolve_audio
    from test_audio_library import wav_file, rights
    library = AudioLibrary(tmp_path / "audio")
    library.register(wav_file(tmp_path / "sound.wav", 1), "speech", rights())
    with pytest.raises(ValueError, match="hash"):
        resolve_audio(Project.model_validate(data()), library.root)
