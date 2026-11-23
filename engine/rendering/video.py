"""Encoding and independent verification of the exported artifact."""
import json
from fractions import Fraction
from pathlib import Path

from engine.core.models import RenderSettings
from engine.rendering.runtime import capture, run_logged


def validate_probe(data: dict, settings: RenderSettings) -> dict:
    streams = [s for s in data.get("streams", []) if s.get("codec_type") == "video"]
    if len(streams) != 1:
        raise ValueError("Expected exactly one video stream")
    if len(data.get("streams", [])) != 1:
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
    return result


def verify_video(path: Path, settings: RenderSettings, ffprobe: Path) -> dict:
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f"Video is missing or empty: {path}")
    data = json.loads(capture([str(ffprobe), "-v", "error", "-count_frames", "-show_streams",
                               "-show_format", "-of", "json", str(path)], timeout=settings.timeout_seconds))
    return validate_probe(data, settings)


def encode_video(directory: Path, settings: RenderSettings, ffmpeg: Path) -> float:
    temporary = directory / "video.partial.mp4"
    elapsed = run_logged([str(ffmpeg), "-nostdin", "-v", "warning", "-y", "-framerate", str(settings.fps),
        "-start_number", "1", "-i", str(directory / "frames" / "%06d.png"),
        "-frames:v", str(settings.frames), "-an", "-c:v", "libx264", "-preset", "medium",
        "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(temporary)],
        directory / "ffmpeg.log", settings.timeout_seconds)
    return elapsed
