"""Explicit expensive test: actual pinned Turbo inference, never a fixture provider."""
import os
from pathlib import Path

import pytest

from engine.audio.validation import verify_wav
from engine.voice.library import VoiceLibrary
from engine.voice.provider import ChatterboxProvider

pytestmark = [pytest.mark.integration, pytest.mark.skipif(os.environ.get("ATLAS_VOICE_INTEGRATION") != "1",
    reason="set ATLAS_VOICE_INTEGRATION=1 for real pinned Turbo inference")]


def test_real_turbo_speech_and_verified_cache(tmp_path):
    root = Path(__file__).resolve().parents[2]
    provider = ChatterboxProvider(Path(os.environ.get("ATLAS_VOICE_PYTHON", root / "outputs/voice-runtime/Scripts/python.exe")),
        model_cache=root / "outputs/voice-models", timeout=600)
    library = VoiceLibrary(tmp_path / "voices")
    library.create_profile("test-narrator")
    result = library.generate("Hello, this is an animation test.", "test-narrator", provider)
    assert result["inference"]["inference_verified"] is True
    measured = verify_wav(Path(result["wav_path"]))
    assert measured["sample_rate"] == 24000 and measured["duration_seconds"] > .2
    assert measured["sha256"] == result["metadata"]["sha256"]
    reused = library.generate("Hello, this is an animation test.", "test-narrator", provider)
    assert reused["cache_hit"] is True
    assert reused["metadata"]["sha256"] == measured["sha256"]
