"""Voice host tests use a deterministic PCM fixture, never real TTS evidence."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import subprocess
import wave

import pytest

from engine.audio.validation import verify_wav
from engine.voice.library import VoiceLibrary, segment_text
from engine.voice.provider import ChatterboxProvider


def tone(path, seconds=0.1, amplitude=1000):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
        wav.writeframes(b"".join(struct.pack("<h", int(amplitude * math.sin(i / 9)))
                                 for i in range(int(seconds * 24000))))


class FixtureProvider:
    """External inference substitute; cache/validation/assembly are production code."""
    identity = {"provider": "test-fixture", "model_revision": "fixture-v1"}
    calls = 0

    def generate(self, segments, outputs, reference, settings):
        self.calls += 1
        for output in outputs:
            tone(output)
        return {"fixture": True}


def test_pcm_metadata_is_measured_and_hashed(tmp_path):
    wav = tmp_path / "a.wav"
    tone(wav)
    result = verify_wav(wav)
    assert result["duration_seconds"] == 0.1
    assert result["frames"] == 2400
    assert result["sample_rate"] == 24000
    assert result["sha256"] == hashlib.sha256(wav.read_bytes()).hexdigest()


def test_truncated_and_silent_pcm_are_rejected(tmp_path):
    wav = tmp_path / "a.wav"
    tone(wav)
    wav.write_bytes(wav.read_bytes()[:-10])
    with pytest.raises(ValueError, match="truncated"):
        verify_wav(wav)
    tone(wav, amplitude=0)
    with pytest.raises(ValueError, match="silent"):
        verify_wav(wav)


def test_reference_requires_consent_is_pinned_and_deleted(tmp_path):
    library = VoiceLibrary(tmp_path / "library")
    reference = tmp_path / "ref.wav"
    tone(reference, 6)
    with pytest.raises(ValueError, match="consent"):
        library.create_profile("speaker", reference=reference)
    profile = library.create_profile("speaker", reference=reference,
        consent={"approved": True, "owner": "Test author", "allowed_usage": "Unit tests",
                 "evidence": "Own original recording"})
    stored = Path(profile["reference"]["path"])
    assert stored != reference and stored.is_file()
    reference.unlink()
    assert library.get_profile("speaker")["reference"]["sha256"]
    with pytest.raises(FileExistsError):
        library.create_profile("speaker")
    library.delete_profile("speaker")
    assert not stored.exists()
    assert library.list_profiles() == []


def test_profiles_reject_path_traversal(tmp_path):
    with pytest.raises(ValueError):
        VoiceLibrary(tmp_path).create_profile("../escape")


def test_segmentation_preserves_words_tags_and_paragraphs():
    result = segment_text("Hello there. Welcome aboard!\n\nA longer sentence with many words.", 24)
    assert all(len(part["text"]) <= 24 for part in result)
    assert any(part["paragraph_end"] for part in result[:-1])
    assert " ".join(part["text"] for part in result) == "Hello there. Welcome aboard! A longer sentence with many words."
    with pytest.raises(ValueError, match="tag"):
        segment_text("Hello [invented] there")


def test_cache_reuses_verified_audio_and_invalidates_corruption_settings_runtime(tmp_path):
    library = VoiceLibrary(tmp_path)
    library.create_profile("narrator")
    provider = FixtureProvider()
    first = library.generate("Hello world.", "narrator", provider)
    assert first["cache_hit"] is False
    assert library.generate("Hello world.", "narrator", provider)["cache_hit"] is True
    assert provider.calls == 1
    Path(first["wav_path"]).write_bytes(b"broken")
    assert library.generate("Hello world.", "narrator", provider)["cache_hit"] is False
    changed = library.generate("Hello world.", "narrator", provider, {"seed": 4})
    assert changed["wav_path"] != first["wav_path"]
    provider.identity = {"provider": "test-fixture", "model_revision": "fixture-v2"}
    assert library.generate("Hello world.", "narrator", provider)["wav_path"] != first["wav_path"]


def test_combined_duration_uses_measured_pcm_and_configured_pause(tmp_path):
    library = VoiceLibrary(tmp_path)
    library.create_profile("narrator")
    result = library.generate("First. Second.", "narrator", FixtureProvider(),
                              {"segment_chars": 8, "pause_ms": 50})
    assert result["metadata"]["duration_seconds"] == 0.25
    assert result["segments"][1]["start_seconds"] == 0.15


def test_missing_runtime_reports_actionable_status(tmp_path):
    provider = ChatterboxProvider(tmp_path / "missing-python.exe")
    result = provider.doctor()
    assert result["ready"] is False
    assert "runtime" in result["error"].lower()
    with pytest.raises(RuntimeError, match="runtime"):
        provider.generate(["Hello."], [tmp_path / "out.wav"], None, {})


def test_cli_profile_lifecycle_and_doctor(tmp_path):
    from apps.cli.voice import add_voice_commands, run_voice_command
    parser = argparse.ArgumentParser()
    add_voice_commands(parser.add_subparsers(dest="command"))
    def run(*args):
        return run_voice_command(parser.parse_args(["voice", *args, "--library", str(tmp_path)]))
    assert run("create", "narrator")["id"] == "narrator"
    assert run("list")["profiles"][0]["id"] == "narrator"
    assert run("delete", "narrator")["deleted"] == "narrator"


def test_changed_reference_is_rejected_before_inference(tmp_path):
    library = VoiceLibrary(tmp_path / "library")
    reference = tmp_path / "ref.wav"
    tone(reference, 6)
    profile = library.create_profile("speaker", reference=reference,
        consent={"approved": True, "owner": "Test author", "allowed_usage": "Tests", "evidence": "Original"})
    tone(Path(profile["reference"]["path"]), 6, amplitude=2000)
    with pytest.raises(ValueError, match="reference has changed"):
        library.generate("Hello.", "speaker", FixtureProvider())


def test_changed_line_keeps_unchanged_segment_and_deletion_removes_generated_cache(tmp_path):
    library = VoiceLibrary(tmp_path)
    library.create_profile("narrator")
    provider = FixtureProvider()
    first = library.generate("Hello. Goodbye.", "narrator", provider)
    second = library.generate("Hello. Welcome.", "narrator", provider)
    assert first["segments"][0]["sha256"] == second["segments"][0]["sha256"]
    assert len(list((tmp_path / "profiles/narrator/segments").glob("*.wav"))) == 3
    library.delete_profile("narrator")
    assert not Path(first["wav_path"]).exists()
    assert not Path(second["wav_path"]).exists()


def test_protocol_boundary_rejects_failure_malformed_json_and_timeout(tmp_path, monkeypatch):
    import engine.voice.provider as provider_module
    provider = ChatterboxProvider(Path(sys.executable), timeout=1)
    for output in ('not json', '{"protocol":1,"ok":false,"error":"model unavailable"}'):
        monkeypatch.setattr(provider_module, "run_worker", lambda *a, **kw: subprocess.CompletedProcess(a, 0, output, "trace"))
        with pytest.raises(RuntimeError):
            provider.generate(["Hello."], [tmp_path / "out.wav"], None, {})
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])
    monkeypatch.setattr(provider_module, "run_worker", timeout)
    with pytest.raises(RuntimeError, match="timed out"):
        provider.generate(["Hello."], [tmp_path / "out.wav"], None, {})
    assert not (tmp_path / "out.wav").exists()


def test_worker_rejects_protocol_without_importing_ml_runtime():
    import engine.voice.worker as worker
    process = subprocess.run([sys.executable, worker.__file__], input='{"protocol":99}',
                             text=True, capture_output=True)
    assert process.returncode == 1
    assert json.loads(process.stdout)["ok"] is False
    assert "protocol" in json.loads(process.stdout)["error"]


def test_output_history_survives_new_library_instance(tmp_path):
    library = VoiceLibrary(tmp_path)
    library.create_profile("narrator")
    generated = library.generate("Hello.", "narrator", FixtureProvider())
    history = VoiceLibrary(tmp_path).history("narrator")
    assert history[0]["cache_key"] == generated["cache_key"]
    assert history[0]["wav_path"] == generated["wav_path"]


def test_known_tags_are_not_split_and_unknown_controls_are_rejected(tmp_path):
    from engine.voice.library import generation_settings
    assert segment_text("Hello [clear throat] there.", 16)[1]["text"] == "[clear throat]"
    for settings in ({"exaggeration": 0.5}, {"temperature": float("nan")}, {"seed": True}):
        with pytest.raises(ValueError):
            generation_settings(settings)


def test_excessively_clipped_pcm_is_rejected(tmp_path):
    wav = tmp_path / "clipped.wav"
    with wave.open(str(wav), "wb") as output:
        output.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
        output.writeframes(struct.pack("<h", 32767) * 100)
    with pytest.raises(ValueError, match="clipped"):
        verify_wav(wav)


def test_forced_generation_preserves_previous_take(tmp_path):
    library = VoiceLibrary(tmp_path)
    library.create_profile("narrator")
    provider = FixtureProvider()
    first = library.generate("Hello.", "narrator", provider)
    second = library.generate("Hello.", "narrator", provider, force=True)
    assert provider.calls == 2
    assert first["wav_path"] != second["wav_path"]
    assert Path(first["wav_path"]).is_file()
    assert len(library.history("narrator")) == 2


def test_model_integrity_rejects_changed_bytes_at_same_revision(tmp_path):
    from engine.voice.model_integrity import verify_model_files
    path = tmp_path / "weights"
    path.write_bytes(b"original")
    expected = {"weights": (8, "sha256", hashlib.sha256(b"original").hexdigest())}
    verify_model_files(tmp_path, expected)
    path.write_bytes(b"modified")
    with pytest.raises(ValueError, match="hash"):
        verify_model_files(tmp_path, expected)
    path.unlink()
    with pytest.raises(ValueError, match="missing"):
        verify_model_files(tmp_path, expected)


def test_malformed_persistent_profile_is_actionable(tmp_path):
    library = VoiceLibrary(tmp_path)
    library.create_profile("narrator")
    path = tmp_path / "profiles/narrator/profile.json"
    value = json.loads(path.read_text()); value.pop("settings")
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="settings"):
        library.get_profile("narrator")
