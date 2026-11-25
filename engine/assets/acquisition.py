"""Bounded acquisition of official source files and dependency-free GLB derivation."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import struct
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zipfile import ZipFile

from engine.assets.glb import inspect_glb
from engine.assets.registry import file_hash
from engine.storage.jobs import atomic_json, contained_path, utc_now

MIB = 1024 * 1024
HOSTS = frozenset({"api.polyhaven.com", "dl.polyhaven.org", "cdn.polyhaven.com",
                   "raw.githubusercontent.com", "codeload.github.com", "creativecommons.org",
                   "ambientcg.com", "acg-download.struffelproductions.com",
                   "3d-api.si.edu",
                   "files.makehumancommunity.org", "files2.makehumancommunity.org"})


def check_url(url: str) -> None:
    parts = urlsplit(url)
    if (parts.scheme != "https" or parts.hostname not in HOSTS or parts.username is not None
            or parts.password is not None or parts.port not in {None, 443} or parts.fragment):
        raise ValueError("Download URL must use an approved HTTPS provider host")


class ProviderRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def request(url):
    check_url(url)
    return build_opener(ProviderRedirect()).open(Request(url, headers={"User-Agent": "ATLAS-Animation/0.5",
        "Accept-Encoding": "identity"}), timeout=25)


def fetch_bytes(url, limit=8 * MIB):
    with request(url) as response:
        if response.headers.get("Content-Encoding", "identity") != "identity":
            raise ValueError("Unexpected compressed provider response")
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Provider response exceeds limit")
    return data


def download(url: str, root: Path, budget: int, *, expected_size=None, expected_md5=None,
             cache_key=None, recorded_url=None, validate_url=None, open_url=None) -> tuple[Path, dict]:
    (validate_url or check_url)(url)
    if recorded_url is not None:
        origin = urlsplit(recorded_url)
        if (origin.scheme != "https" or not origin.hostname or origin.query or origin.fragment
                or origin.username is not None or origin.password is not None or origin.port not in {None, 443}):
            raise ValueError("Persistent source identity must be a public HTTPS URL without credentials or parameters")
    if not 1 <= budget <= 512 * MIB:
        raise ValueError("Download budget must be 1 byte to 512 MiB")
    if expected_size is not None and not 1 <= expected_size <= budget:
        raise ValueError("File size exceeds the configured download budget")
    started = time.monotonic()
    key = hashlib.sha256((cache_key or url).encode()).hexdigest()
    pointer = contained_path(root, f"downloads/{key}.json")
    if pointer.is_file():
        previous = json.loads(pointer.read_text(encoding="utf-8"))
        digest = previous["sha256"]
        if re.fullmatch(r"[a-f0-9]{64}", digest):
            blob = contained_path(root, f"blobs/{digest}")
            if (blob.is_file() and blob.stat().st_size == previous["bytes"] <= budget
                    and (expected_size is None or expected_size == previous["bytes"])
                    and (expected_md5 is None or expected_md5 == previous.get("md5"))
                    and file_hash(blob) == digest):
                return blob, previous | {"cache_hit": True, "seconds": time.monotonic() - started}
    root.mkdir(parents=True, exist_ok=True)
    blobs = contained_path(root, "blobs")
    blobs.mkdir(exist_ok=True)
    if shutil.disk_usage(root).free < (expected_size or budget) + 32 * MIB:
        raise ValueError("Insufficient free space for bounded download")
    for attempt in range(3):
        temporary = None
        try:
            with (open_url or request)(url) as response, tempfile.NamedTemporaryFile(dir=blobs, delete=False) as stream:
                temporary = Path(stream.name)
                if response.headers.get("Content-Encoding", "identity") != "identity":
                    raise ValueError("Unexpected compressed provider download")
                length = response.headers.get("Content-Length")
                if length is not None and not 0 < int(length) <= budget:
                    raise ValueError("Provider content length exceeds download budget")
                digest, md5, size = hashlib.sha256(), hashlib.md5(usedforsecurity=False), 0
                while chunk := response.read(256 * 1024):
                    size += len(chunk)
                    if size > budget or time.monotonic() - started > 240:
                        raise ValueError("Download exceeded byte or time limit")
                    digest.update(chunk)
                    md5.update(chunk)
                    stream.write(chunk)
                stream.flush()
                os.fsync(stream.fileno())
            if not size or (length and size != int(length)) or (expected_size is not None and size != expected_size):
                raise ValueError("Download size mismatch")
            if expected_md5 is not None and md5.hexdigest() != expected_md5.lower():
                raise ValueError("Provider file checksum mismatch")
            identity = digest.hexdigest()
            blob = contained_path(root, f"blobs/{identity}")
            temporary.replace(blob)
            record = {"url": recorded_url or url, "sha256": identity, "md5": md5.hexdigest(), "bytes": size,
                      "downloaded_at": utc_now(), "seconds": time.monotonic() - started, "cache_hit": False}
            atomic_json(pointer, record)
            return blob, record
        except HTTPError as exc:
            if exc.code not in {500, 502, 503, 504} or attempt == 2:
                raise
        except (URLError, TimeoutError):
            if attempt == 2:
                raise
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        time.sleep(2 ** attempt)
    raise RuntimeError("Download retries exhausted")


def unpack_models(archive: ZipFile, *, allow_scripts: bool = False) -> dict:
    """Validate the entire directory. Only callers' selected files are read into memory."""
    entries = archive.infolist()
    if len(entries) > 10000 or sum(i.file_size for i in entries) > 512 * MIB:
        raise ValueError("Archive exceeds entry or inflated-size budget")
    files, keys = {}, set()
    for item in entries:
        name = item.filename.rstrip("/")
        parts = name.split("/")
        if any(not p or p in {".", ".."} or p.endswith((".", " ")) or re.search(r'[:\\<>|?*"\x00-\x1f]', p)
               for p in parts):
            raise ValueError(f"Unsafe archive path: {name}")
        key = name.casefold()
        if key in keys or item.orig_filename != item.filename:
            raise ValueError("Archive has duplicate or nonportable paths")
        keys.add(key)
        mode = stat.S_IFMT(item.external_attr >> 16)
        if mode not in {0, stat.S_IFREG, stat.S_IFDIR} or item.flag_bits & 1:
            raise ValueError("Archive contains a linked, special or encrypted entry")
        if item.file_size > 128 * MIB or item.file_size > max(item.compress_size * 500, MIB):
            raise ValueError("Archive entry exceeds size or compression-ratio budget")
        if not item.is_dir():
            suffix = PurePosixPath(name).suffix.lower()
            if suffix in {".exe", ".dll", ".msi", ".bat", ".ps1", ".cmd", ".sh", ".scr"} or (suffix == ".py" and not allow_scripts):
                raise ValueError("Archive contains an executable or script")
            files[name] = item
    return files


def pack_gltf(payload: bytes, read_dependency, *, texture_subdirectory: bool = False) -> bytes:
    """Embed one external BIN buffer and PNG/JPEG images without decoding them."""
    if len(payload) > 8 * MIB:
        raise ValueError("glTF JSON exceeds 8 MiB")
    doc = json.loads(payload)
    if not isinstance(doc, dict) or doc.get("asset", {}).get("version") != "2.0" or len(doc.get("buffers", [])) != 1:
        raise ValueError("Expected glTF 2.0 with one external binary buffer")

    def read(uri, suffixes, *, image=False):
        name = uri
        if image and texture_subdirectory and isinstance(uri, str):
            name = uri.removeprefix("textures/")
        if (not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9_. -]{0,199}", name)
                or PurePosixPath(name).suffix.lower() not in suffixes):
            raise ValueError("Unsafe glTF dependency filename")
        data = read_dependency(uri)
        if not isinstance(data, bytes) or not 0 < len(data) <= 128 * MIB:
            raise ValueError(f"Missing or oversized glTF dependency: {uri}")
        return data

    buffer = doc["buffers"][0]
    binary = bytearray(read(buffer.pop("uri", None), {".bin"}))
    if len(binary) != buffer["byteLength"]:
        raise ValueError("glTF buffer length mismatch")
    views = doc.setdefault("bufferViews", [])
    for image in doc.get("images", []):
        uri = image.pop("uri", None)
        data = read(uri, {".png", ".jpg", ".jpeg"}, image=True)
        mime = "image/png" if uri.lower().endswith(".png") else "image/jpeg"
        if not data.startswith(b"\x89PNG\r\n\x1a\n" if mime == "image/png" else b"\xff\xd8\xff"):
            raise ValueError("glTF texture signature does not match its file type")
        binary.extend(b"\0" * (-len(binary) % 4))
        if len(binary) + len(data) > 128 * MIB:
            raise ValueError("Embedded GLB resource budget exceeded")
        image.update(bufferView=len(views), mimeType=mime)
        views.append({"buffer": 0, "byteOffset": len(binary), "byteLength": len(data)})
        binary.extend(data)
    buffer["byteLength"] = len(binary)
    return _encode_glb(doc, binary)


def _encode_glb(document: dict, binary: bytes | bytearray) -> bytes:
    header = json.dumps(document, separators=(",", ":"), allow_nan=False).encode()
    header += b" " * (-len(header) % 4)
    chunks = struct.pack("<II", len(header), 0x4E4F534A) + header
    if binary:
        padded_size = len(binary) + (-len(binary) % 4)
        chunks += struct.pack("<II", padded_size, 0x004E4942) + binary + b"\0" * (padded_size - len(binary))
    return struct.pack("<4sII", b"glTF", 2, 12 + len(chunks)) + chunks


def scale_static_glb(path: Path, meters_per_unit: float) -> bytes:
    """Add a unit conversion at the root of an already validated static GLB."""
    inspect_glb(path, "static")
    with path.open("rb") as handle:
        handle.seek(12)
        json_size, _ = struct.unpack("<II", handle.read(8))
        doc = json.loads(handle.read(json_size))
        binary_header = handle.read(8)
        binary = handle.read(struct.unpack("<II", binary_header)[0]) if binary_header else b""
    nodes, scene = doc["nodes"], doc["scenes"][0]
    roots = scene["nodes"]
    scene["nodes"] = [len(nodes)]
    nodes.append({"scale": [meters_per_unit] * 3, "children": roots})
    return _encode_glb(doc, binary)


def read_archive_model(path: Path, member: str) -> bytes:
    """Read one explicitly selected GLB or same-directory glTF and resources."""
    if not path.is_file() or not 0 < path.stat().st_size <= 128 * MIB:
        raise ValueError("A local ZIP no larger than 128 MiB is required")
    with ZipFile(path) as archive:
        members = unpack_models(archive)
        return archive_model(archive, members, member)


def archive_model(archive: ZipFile, members: dict, member: str, *, texture_subdirectory: bool = False) -> bytes:
    suffix = PurePosixPath(member).suffix.lower()
    if member not in members or suffix not in {".gltf", ".glb"}:
        raise ValueError("Selected archive member must be an existing GLB or glTF")
    body = archive.read(members[member])
    if suffix == ".glb":
        return body
    parent = PurePosixPath(member).parent

    def dependency(name):
        resource = members.get(str(parent / name))
        return archive.read(resource) if resource else None

    return pack_gltf(body, dependency, texture_subdirectory=texture_subdirectory)
