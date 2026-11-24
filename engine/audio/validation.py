"""Bounded PCM WAV inspection, independent of FFmpeg and ML runtimes."""
from array import array
import hashlib
from pathlib import Path
import sys
import wave


def verify_wav(path: Path) -> dict:
    path = Path(path)
    size = path.stat().st_size
    if size > 256 * 1024 * 1024:
        raise ValueError("WAV exceeds 256 MiB validation limit")
    try:
        with wave.open(str(path), "rb") as wav:
            channels, width, rate, frames = (wav.getnchannels(), wav.getsampwidth(),
                                            wav.getframerate(), wav.getnframes())
            if width != 2 or channels not in (1, 2) or not 8000 <= rate <= 192000:
                raise ValueError("Expected mono/stereo PCM16 WAV at 8–192 kHz")
            if frames <= 0 or frames / rate > 3600:
                raise ValueError("WAV must contain 0–3600 seconds of audio")
            expected = frames * channels * width
            if expected > size:
                raise ValueError("WAV is truncated")
            data = wav.readframes(frames)
            if len(data) != expected:
                raise ValueError("WAV is truncated")
    except (wave.Error, EOFError) as error:
        raise ValueError(f"Invalid PCM WAV: {error}") from error
    samples = array("h", data)
    if sys.byteorder != "little":
        samples.byteswap()
    peak = max(abs(sample) for sample in samples)
    clipped = sum(sample in (-32768, 32767) for sample in samples)
    if peak <= 1:
        raise ValueError("WAV is silent")
    if clipped / len(samples) > 0.01:
        raise ValueError("WAV is pathologically clipped (>1% full-scale samples)")
    with path.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    return {"duration_seconds": frames / rate, "sample_rate": rate, "channels": channels,
            "sample_width": width, "frames": frames, "peak": peak / 32768,
            "clipped_samples": clipped, "sha256": digest}
