"""Encoding and independent verification of the exported artifact."""
import json
from fractions import Fraction
from pathlib import Path

from engine.core.models import RenderSettings
from engine.rendering.runtime import capture, run_logged


def validate_probe(data: dict, settings: RenderSettings, *, expect_audio: bool = False) -> dict:
    streams = [s for s in data.get("streams", []) if s.get("codec_type") == "video"]
    if len(streams) != 1:
        raise ValueError("Expected exactly one video stream")
    if not expect_audio and len(data.get("streams", [])) != 1:
        raise ValueError("This release expects silent video without additional streams")
    container = data.get("format", {})
    if "mp4" not in container.get("format_name", "").split(","):
        raise ValueError("Expected an MP4 container")
    try:
        container_duration = float(container["duration"])
    except (KeyError, ValueError, TypeError) as exc:
        raise ValueError("Missing or invalid container duration") from exc
    if not abs(container_duration - settings.frames / settings.fps) <= 0.5 / settings.fps:
        raise ValueError(f"Container duration mismatch: {container_duration}")
    stream = streams[0]
    try:
        result = {"width": int(stream["width"]), "height": int(stream["height"]),
                  "frames": int(stream["nb_read_frames"]),
                  "fps": float(Fraction(stream["avg_frame_rate"])),
                  "duration": float(stream["duration"]), "codec": stream["codec_name"],
                  "pixel_format": stream["pix_fmt"]}
    except (KeyError, ValueError, TypeError, ZeroDivisionError) as exc:
        raise ValueError(f"Incomplete ffprobe video metadata: {exc}") from exc
    for field, expected in (("width", settings.width), ("height", settings.height),
                            ("frames", settings.frames), ("codec", "h264"), ("pixel_format", "yuv420p")):
        if result[field] != expected:
            raise ValueError(f"Video {field}: expected {expected}, got {result[field]}")
    if abs(result["fps"] - settings.fps) > 0.001:
        raise ValueError(f"Video frame rate mismatch: {result['fps']}")
    if not abs(result["duration"] - settings.frames / settings.fps) <= 0.5 / settings.fps:
        raise ValueError(f"Video duration mismatch: {result['duration']}")
    if expect_audio:
        audio = [s for s in data.get("streams", []) if s.get("codec_type") == "audio"]
        if len(audio) != 1 or len(data["streams"]) != 2:
            raise ValueError("Expected exactly one video and one audio stream")
        try:
            a = audio[0]
            sound = {"codec": a["codec_name"], "sample_rate": int(a["sample_rate"]), "channels": int(a["channels"]),
                     "duration": float(a["duration"]), "start_time": float(a["start_time"])}
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError("Incomplete audio stream metadata") from exc
        if sound["codec"] != "aac" or sound["sample_rate"] != 48000 or sound["channels"] != 2:
            raise ValueError("Expected AAC, 48000 Hz stereo audio")
        if not abs(sound["duration"] - settings.frames / settings.fps) <= max(.05, .5 / settings.fps):
            raise ValueError("Audio duration does not match video")
        if not abs(sound["start_time"]) <= .025:
            raise ValueError("Audio stream starts out of sync")
        result["audio"] = sound
    return result


def verify_video(path: Path, settings: RenderSettings, ffprobe: Path, *, expect_audio: bool = False) -> dict:
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f"Video is missing or empty: {path}")
    data = json.loads(capture([str(ffprobe), "-v", "error", "-count_frames", "-show_streams",
                               "-show_format", "-of", "json", str(path)], timeout=settings.timeout_seconds))
    return validate_probe(data, settings, expect_audio=expect_audio)


def encode_video(directory: Path, settings: RenderSettings, ffmpeg: Path) -> float:
    temporary = directory / "video.partial.mp4"
    elapsed = run_logged([str(ffmpeg), "-nostdin", "-v", "warning", "-y", "-framerate", str(settings.fps),
        "-start_number", "1", "-i", str(directory / "frames" / "%06d.png"),
        "-frames:v", str(settings.frames), "-an", "-c:v", "libx264", "-preset", "medium",
        "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(temporary)],
        directory / "ffmpeg.log", settings.timeout_seconds)
    return elapsed
