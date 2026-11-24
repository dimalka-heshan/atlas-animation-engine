"""Isolated Rhubarb CLI adapter. No inferred timings or text-length fallback."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import wave

from .models import LipSyncTimeline

PINNED_VERSION = '1.14.0'


def resolve_executable(executable=None) -> Path:
    configured = executable or os.environ.get('ATLAS_RHUBARB') or shutil.which('rhubarb')
    if not configured or not Path(configured).is_file():
        raise FileNotFoundError('Rhubarb executable missing; install official 1.14.0 and set ATLAS_RHUBARB or --executable')
    return Path(configured).resolve()


def doctor(executable=None) -> dict:
    path = resolve_executable(executable)
    result = subprocess.run([str(path), '--version'], capture_output=True, text=True, timeout=15, check=True)
    match = re.search(r'\b(\d+\.\d+\.\d+)\b', result.stdout + result.stderr)
    if not match or match[1] != PINNED_VERSION:
        raise ValueError(f'Rhubarb {PINNED_VERSION} required; received {result.stdout.strip()}')
    return {'executable': str(path), 'version': match[1],
            'executable_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'recognizer': 'pocketSphinx', 'precision': 'coarse mouth cues; not precise phonemes'}


def parse_result(raw: dict, audio_sha256: str, duration: float, version: str) -> LipSyncTimeline:
    # Rhubarb exports centisecond duration. Only reconcile that known quantization.
    try:
        reported = float(raw['metadata']['duration'])
        cues = [dict(cue) for cue in raw['mouthCues']]
        if len(cues) > 10000:
            raise ValueError('Too many cues')
        if cues and abs(float(cues[-1]['end']) - duration) <= .011:
            cues[-1]['end'] = duration
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f'Malformed Rhubarb response: {exc}') from exc
    if not abs(reported - duration) <= .011:
        raise ValueError('Rhubarb duration disagrees with measured WAV duration')
    if not cues:
        raise ValueError('Rhubarb returned no mouth cues')
    return LipSyncTimeline(audio_sha256=audio_sha256, duration_seconds=duration,
                           cues=cues, method='rhubarb', version=version)


def align_wav(audio: Path, transcript: str, output: Path, executable=None) -> LipSyncTimeline:
    audio, output = Path(audio).resolve(), Path(output).resolve()
    if audio == output:
        raise ValueError('Timeline output must not replace its source WAV')
    if not isinstance(transcript, str) or not transcript.strip() or len(transcript) > 100000:
        raise ValueError('A nonempty English transcript of at most 100000 characters is required')
    if audio.stat().st_size > 64 * 1024 * 1024:
        raise ValueError('Alignment WAV exceeds 64 MiB')
    try:
        with wave.open(str(audio), 'rb') as stream:
            if stream.getcomptype() != 'NONE' or stream.getnframes() == 0 or stream.getsampwidth() != 2 or stream.getnchannels() not in (1, 2):
                raise ValueError('Lip-sync requires nonempty mono/stereo PCM16 WAV audio')
            duration = stream.getnframes() / stream.getframerate()
            if not 0 < duration <= 180:
                raise ValueError('Lip-sync supports at most 180 seconds per audio clip')
            frames = stream.readframes(stream.getnframes())
            if len(frames) != stream.getnframes() * stream.getnchannels() * stream.getsampwidth():
                raise ValueError('Truncated WAV sample data')
    except (wave.Error, EOFError) as exc:
        raise ValueError(f'Invalid alignment WAV: {exc}') from exc
    digest = hashlib.sha256(audio.read_bytes()).hexdigest()
    info = doctor(executable)
    with tempfile.TemporaryDirectory(prefix='atlas-lipsync-') as folder:
        dialog, result_path = Path(folder) / 'dialog.txt', Path(folder) / 'result.json'
        dialog.write_text(transcript, encoding='utf-8')
        command = [info['executable'], '-f', 'json', '-r', 'pocketSphinx', '--extendedShapes', 'GHX',
                   '-d', str(dialog), '-o', str(result_path), str(audio)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=600)
        if result.returncode:
            raise ValueError(f'Rhubarb alignment failed ({result.returncode}): {result.stderr[-2000:]}')
        if not result_path.is_file() or result_path.stat().st_size > 5 * 1024 * 1024:
            raise ValueError('Missing or oversized Rhubarb output')
        timeline = parse_result(json.loads(result_path.read_text(encoding='utf-8')), digest, duration, info['version'])
    if hashlib.sha256(audio.read_bytes()).hexdigest() != digest:
        raise ValueError('Source WAV changed during alignment')
    timeline.transcript_sha256 = hashlib.sha256(transcript.encode('utf-8')).hexdigest()
    timeline.executable_sha256 = info['executable_sha256']
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=output.parent, delete=False) as temp:
        temp.write(timeline.model_dump_json(indent=2) + '\n')
        temporary = Path(temp.name)
    try:
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    return timeline
