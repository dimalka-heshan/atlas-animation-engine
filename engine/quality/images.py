"""Verify actual PNG dimensions and decoded image variation with FFmpeg."""
import json
import subprocess
import struct
import zlib
from pathlib import Path

from engine.rendering.runtime import capture, find_tool


def validate_png_structure(path: Path, size: int) -> None:
    """Check bounded framing and every CRC; tolerant decoders alone miss damage."""
    with path.open("rb") as handle:
        data = handle.read(16 * 1024 * 1024 + 1)
    if len(data) > 16 * 1024 * 1024 or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Invalid PNG signature or thumbnail exceeds 16 MiB")
    offset, chunks, seen_data, data_ended = 8, 0, False, False
    while offset < len(data):
        chunks += 1
        if chunks > 10000 or offset + 12 > len(data):
            raise ValueError("Invalid PNG chunk framing")
        length, kind = struct.unpack_from(">I4s", data, offset)
        end = offset + 12 + length
        if end > len(data):
            raise ValueError("Truncated PNG chunk")
        payload = data[offset + 8:end - 4]
        crc = struct.unpack_from(">I", data, end - 4)[0]
        if zlib.crc32(kind + payload) & 0xffffffff != crc:
            raise ValueError("PNG chunk checksum mismatch")
        if chunks == 1:
            if kind != b"IHDR" or length != 13 or struct.unpack_from(">II", payload) != (size, size):
                raise ValueError("PNG header does not match thumbnail dimensions")
        elif kind == b"IHDR":
            raise ValueError("Duplicate PNG header")
        if kind == b"IDAT":
            if data_ended:
                raise ValueError("Noncontiguous PNG image data")
            seen_data = True
        elif seen_data:
            data_ended = True
        if kind == b"IEND":
            if length or end != len(data) or not seen_data:
                raise ValueError("Invalid PNG ending")
            return
        offset = end
    raise ValueError("PNG is missing its IEND chunk")


def validate_png_probe(data: dict, size: int) -> dict:
    streams = data.get("streams", [])
    if len(streams) != 1:
        raise ValueError("Expected exactly one PNG image stream")
    stream = streams[0]
    if stream.get("codec_name") != "png" or stream.get("width") != size or stream.get("height") != size:
        raise ValueError(f"Expected a {size}x{size} PNG thumbnail")
    return {"codec": "png", "width": size, "height": size}


def verify_png(path: Path, size: int, *, timeout: int = 30) -> dict:
    """Probe before decoding, bounding raw output to the supported dimensions."""
    if type(size) is not int or size not in {128, 256, 512}:
        raise ValueError("Thumbnail size must be 128, 256 or 512")
    if not path.is_file() or not path.stat().st_size:
        raise ValueError(f"PNG is missing or empty: {path}")
    validate_png_structure(path, size)
    probe = json.loads(capture([str(find_tool("ffprobe")), "-v", "error", "-show_entries",
                               "stream=codec_name,width,height", "-of", "json", str(path)], timeout=timeout))
    result = validate_png_probe(probe, size)
    decoded = subprocess.run([str(find_tool("ffmpeg")), "-nostdin", "-v", "error", "-xerror", "-i", str(path),
                              "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
                             capture_output=True, timeout=timeout, check=False)
    if decoded.returncode:
        raise ValueError(f"PNG decode failed: {decoded.stderr.decode('utf-8', errors='replace')[-2000:]}")
    if len(decoded.stdout) != size * size * 3:
        raise ValueError("PNG decoded to an unexpected pixel count")
    low, high = min(decoded.stdout), max(decoded.stdout)
    spatial_range = max(max(decoded.stdout[channel::3]) - min(decoded.stdout[channel::3]) for channel in range(3))
    if spatial_range <= 8:
        raise ValueError("PNG is black or nearly uniform; thumbnail quality check failed")
    return result | {"pixel_min": low, "pixel_max": high, "spatial_range": spatial_range, "file_bytes": path.stat().st_size}
