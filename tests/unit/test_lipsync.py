import importlib
import json
import math
import wave

import pytest


def models():
    assert importlib.util.find_spec('engine.lipsync'), 'Lip-sync package must exist'
    return importlib.import_module('engine.lipsync.models')


def timeline(**overrides):
    return dict(audio_sha256='a' * 64, duration_seconds=1.0,
                cues=[dict(start=0, end=.4, value='C'), dict(start=.4, end=1, value='X')],
                method='rhubarb', version='1.14.0', **overrides)


@pytest.mark.parametrize('changes', [
    {'cues': []}, {'duration_seconds': float('nan')}, {'audio_sha256': 'bad'},
    {'cues': [dict(start=0, end=2, value='C')]},
    {'cues': [dict(start=0, end=.8, value='C'), dict(start=.7, end=1, value='X')]},
    {'cues': [dict(start=.1, end=1, value='C')]},
    {'cues': [dict(start=0, end=1, value='Q')]},
])
def test_timeline_rejects_invalid_or_uncovered_audio(changes):
    cls = models().LipSyncTimeline
    data = timeline()
    data.update(changes)
    with pytest.raises(ValueError):
        cls.model_validate(data)


def test_timeline_accepts_measured_cues():
    value = models().LipSyncTimeline.model_validate(timeline())
    assert value.cues[1].value == 'X'


def test_rhubarb_parser_preserves_cues_and_measured_duration():
    models()
    parse = importlib.import_module('engine.lipsync.rhubarb').parse_result
    raw = {'metadata': {'duration': 1.0}, 'mouthCues': [
        {'start': 0, 'end': .3, 'value': 'A'},
        {'start': .3, 'end': 1, 'value': 'X'}]}
    result = parse(raw, 'b' * 64, 1.004, '1.14.0')
    assert result.duration_seconds == 1.004
    assert result.cues[-1].end == 1.004
    assert result.cues[0].end == .3
    raw['metadata']['duration'] = 2
    with pytest.raises(ValueError, match='duration'):
        parse(raw, 'b' * 64, 1.004, '1.14.0')


def test_alignment_missing_executable_leaves_no_timeline(tmp_path):
    models()
    align = importlib.import_module('engine.lipsync').align_wav
    wav = tmp_path / 'audio.wav'
    with wave.open(str(wav), 'wb') as stream:
        stream.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        stream.writeframes(b'\0\0' * 16000)
    output = tmp_path / 'timeline.json'
    with pytest.raises((ValueError, FileNotFoundError), match='Rhubarb|rhubarb'):
        align(wav, 'Hello', output, executable=tmp_path / 'absent.exe')
    assert not output.exists()


def test_frame_schedule_has_no_rounding_drift_and_rest_at_end():
    assert importlib.util.find_spec('engine.adapters.blender.facial'), 'Facial adapter must exist'
    facial = importlib.import_module('engine.adapters.blender.facial')
    keys = facial.performance_keys(timeline(), start_seconds=.25, fps=24, smoothing_seconds=.04)
    assert keys[0] == (7.0, 'X')
    assert keys[-1] == (31.0, 'X')
    assert any(math.isclose(frame, 16.6) for frame, _ in keys)
    assert all(keys[i][0] <= keys[i+1][0] for i in range(len(keys)-1))


def test_cli_validate_checks_file_not_just_json(tmp_path):
    import argparse
    assert importlib.util.find_spec('apps.cli.lipsync'), 'Lip-sync CLI must exist'
    cli = importlib.import_module('apps.cli.lipsync')
    parser = argparse.ArgumentParser()
    cli.add_lipsync_commands(parser.add_subparsers(dest='command'))
    path = tmp_path / 'timeline.json'
    path.write_text(json.dumps(timeline()))
    result = cli.run_lipsync_command(parser.parse_args(['lipsync', 'validate', str(path)]))
    assert result['duration_seconds'] == 1
    path.write_text(json.dumps({**timeline(), 'duration_seconds': .2}))
    with pytest.raises(ValueError):
        cli.run_lipsync_command(parser.parse_args(['lipsync', 'validate', str(path)]))


def test_facial_controls_reject_missing_cues_and_nonrest_jaw():
    model = models()
    assert hasattr(model, 'FacialControls'), 'Typed controls must exist'
    with pytest.raises(ValueError):
        model.FacialControls(kind='shape_keys', object='Mouth', mapping={'A': 'Closed'})
    with pytest.raises(ValueError):
        model.FacialControls(kind='jaw_bone', object='Rig', bone='Jaw', angles=dict.fromkeys('ABCDEFGHX', .2))


def test_adjacent_speech_crossfades_without_false_rest():
    from engine.adapters.blender.facial import performance_keys
    data = timeline()
    data['cues'][1]['value'] = 'D'
    keys = performance_keys(data, 0, 24)
    assert not any(value == 'X' and 1 < frame < 25 for frame, value in keys)


def test_timeline_resource_bounds_and_control_unknown_fields():
    cls = models().LipSyncTimeline
    data = timeline()
    data.update(duration_seconds=181, cues=[dict(start=0, end=181, value='X')])
    with pytest.raises(ValueError):
        cls.model_validate(data)
    data.update(duration_seconds=1, cues=[dict(start=i / 10001, end=(i+1) / 10001, value='X') for i in range(10001)])
    with pytest.raises(ValueError):
        cls.model_validate(data)
    with pytest.raises(ValueError):
        models().FacialControls(kind='shape_keys', object='Mouth', mapping={c:c for c in 'ABCDEFGH'}, command='unsafe')


def test_aligner_rejects_excess_duration_before_launch(tmp_path, monkeypatch):
    import wave
    import engine.lipsync.rhubarb as rhubarb
    audio = tmp_path / 'too-long.wav'
    with wave.open(str(audio), 'wb') as stream:
        stream.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
        stream.writeframes(b'\0\0' * (8000 * 181))
    monkeypatch.setattr(rhubarb, 'doctor', lambda *_: pytest.fail('Must validate before starting aligner'))
    with pytest.raises(ValueError, match='180'):
        rhubarb.align_wav(audio, 'Test.', tmp_path / 'result.json')


def test_malformed_aligner_result_is_actionable():
    from engine.lipsync.rhubarb import parse_result
    with pytest.raises(ValueError, match='Rhubarb'):
        parse_result({}, 'a' * 64, 1, '1.14.0')

