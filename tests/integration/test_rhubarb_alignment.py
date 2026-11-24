"""Opt-in real official Rhubarb recognition, never fabricated cue output."""
import hashlib
import os
from pathlib import Path
import wave

import pytest

from engine.lipsync import align_wav

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(os.environ.get('ATLAS_INTEGRATION') != '1', reason='set ATLAS_INTEGRATION=1')]


def test_real_rhubarb_recognizes_fixture_and_silence(tmp_path):
    root = Path(__file__).resolve().parents[2]
    executable = Path(os.environ.get('ATLAS_RHUBARB', root / 'outputs/runtimes/rhubarb/Rhubarb-Lip-Sync-1.14.0-Windows/rhubarb.exe'))
    fixture = root / 'outputs/lipsync-demo/windows-sapi-test.wav'
    transcript = root / 'outputs/lipsync-demo/transcript.txt'
    if not executable.is_file() or not fixture.is_file():
        pytest.skip('Run tools/install_rhubarb.ps1 and tools/create_lipsync_fixture.ps1')
    result = align_wav(fixture, transcript.read_text(encoding='utf-8-sig'), tmp_path / 'speech.json', executable)
    assert result.audio_sha256 == hashlib.sha256(fixture.read_bytes()).hexdigest()
    with wave.open(str(fixture), 'rb') as stream:
        assert result.duration_seconds == stream.getnframes() / stream.getframerate()
    assert len({cue.value for cue in result.cues} - {'X'}) >= 3
    assert result.cues[-1].value == 'X'
    silence = tmp_path / 'silence.wav'
    with wave.open(str(silence), 'wb') as stream:
        stream.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        stream.writeframes(b'\0\0' * 16000)
    result = align_wav(silence, '[silence]', tmp_path / 'silence.json', executable)
    assert all(cue.value == 'X' for cue in result.cues)

