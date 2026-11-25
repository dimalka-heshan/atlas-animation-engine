"""Import a locally staged Blendkit download into the inspected static asset library."""
import hashlib
import json
import os
import re
import stat
import struct
import tempfile
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from engine.assets.glb import inspect_glb
from engine.assets.inspection import inspect_asset
from engine.assets.models import Provenance
from engine.assets.registry import ID, AssetRegistry, file_hash
from engine.rendering.runtime import find_tool, run_logged
from engine.storage.jobs import atomic_json, contained_path, utc_now


ADDON_VERSION = "3.21.7.261119"
ADDON_URL = f"https://github.com/BlenderKit/Blendkit/releases/tag/v{ADDON_VERSION}"
ADDON_SHA256 = "762c731f1d530a9adf1304ffe60b3de8465e9f370815f5eec541a3cec00477c5"
LICENSE_URL = "https://www.blendkit.com/docs/licenses/"
TERMS_URL = "https://www.blendkit.com/terms-and-conditions-2026/"
PROFILE = "atlas-native-static-1"
MAX_BLEND_BYTES = 256 * 1024 * 1024
MAX_BLOCKS = 500_000
ASSET_HOSTS = {"blendkit.com", "www.blendkit.com", "blenderkit.com", "www.blenderkit.com"}


def _require_approval(provider_asset_id: str, plan: str, provenance: Provenance) -> str:
    if plan != "free":
        raise ValueError("Blendkit import requires a reviewed free-plan asset")
    if provenance.license_id != "CC0-1.0":
        raise ValueError("Blendkit editable import requires CC0-1.0; royalty-free assets are ineligible")
    provenance.require_render_rights()
    if provenance.redistribution_allowed:
        raise ValueError("The Blendkit private import workflow requires redistribution_allowed=false")
    try:
        identifier = str(UUID(provider_asset_id))
        source = urlsplit(provenance.source_url)
        if (source.scheme == "https" and source.netloc in ASSET_HOSTS
                and source.path.rstrip("/") == f"/asset-gallery-detail/{identifier}"
                and not source.query and not source.fragment):
            return identifier
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("Blendkit provenance requires a UUID and matching official asset page") from exc
    raise ValueError("Blendkit provenance requires the matching official HTTPS asset page URL without a query")


def _selection(objects: tuple[str, ...], collections: tuple[str, ...]) -> dict:
    if bool(objects) == bool(collections):
        raise ValueError("Select object names or collection names from the Blendkit .blend file")
    key, names = ("objects", objects) if objects else ("collections", collections)
    if (len(names) > 128 or any(not isinstance(name, str) or not name.strip() or len(name) > 255
                               or any(ord(c) < 32 for c in name) for name in names)):
        raise ValueError("Provide at most 128 non-empty Blender data-block names without control characters")
    if len(set(names)) != len(names):
        raise ValueError("Blender data-block selection contains duplicate names")
    return {key: sorted(names)}


def _snapshot(source: Path, destination: Path) -> str:
    if source.suffix.lower() != ".blend" or source.is_symlink() or not source.is_file():
        raise ValueError("Blendkit source must be an existing local regular .blend file")
    digest = hashlib.sha256()
    with source.open("rb") as original:
        info = os.fstat(original.fileno())
        if not stat.S_ISREG(info.st_mode) or not 17 <= info.st_size <= MAX_BLEND_BYTES:
            raise ValueError("Native source must be a regular .blend file up to 256 MiB")
        size = 0
        with destination.open("xb") as copy:
            while chunk := original.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_BLEND_BYTES:
                    raise ValueError("Native source exceeds 256 MiB")
                digest.update(chunk)
                copy.write(chunk)
    if size != info.st_size:
        raise ValueError("Native source changed during snapshot")
    return digest.hexdigest()


def _check_container(path: Path) -> None:
    """Sweep outer block headers before Blender can resolve any linked libraries."""
    size = path.stat().st_size
    with path.open("rb") as source:
        header = source.read(17)
        if re.fullmatch(rb"BLENDER17-01v[0-9]{4}", header):
            block = struct.Struct("<4s12xq8x")
        elif re.fullmatch(rb"BLENDER-v[0-9]{3}", header[:12]):
            source.seek(12)
            block = struct.Struct("<4si16x")
        else:
            raise ValueError("Use a supported uncompressed little-endian 64-bit .blend file")
        has_schema = False
        for _ in range(MAX_BLOCKS):
            raw = source.read(block.size)
            if raw == b"ENDB\0\0\0\0" and source.tell() == size and has_schema:
                return  # Legacy files can use a short end marker.
            if len(raw) != block.size:
                raise ValueError("Native .blend file has a truncated block header")
            code, length = block.unpack(raw)
            if length < 0 or length > size - source.tell():
                raise ValueError("Native .blend file has an invalid block length")
            if code in {b"LI\0\0", b"ID\0\0"}:
                raise ValueError("Native .blend file contains linked libraries")
            if code == b"TX\0\0":
                raise ValueError("Native .blend file contains embedded text blocks")
            if code == b"USER":
                raise ValueError("Native .blend file contains user preferences")
            if code == b"ENDB":
                if length or source.tell() != size or not has_schema:
                    raise ValueError("Native .blend file has invalid or trailing file data")
                return
            has_schema |= code == b"DNA1"
            source.seek(length, os.SEEK_CUR)
    raise ValueError("Native .blend file exceeds its block budget")


def _isolated_environment(workspace: Path) -> dict:
    # Blender resolves OS libraries on Windows via these variables. The worker needs no provider credentials.
    system = {"SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATH", "PATHEXT", "DISPLAY", "LANG", "LC_ALL"}
    profile = workspace / "profile"
    profile.mkdir()
    return {key: value for key, value in os.environ.items() if key.upper() in system} | {
        "BLENDER_USER_RESOURCES": str(profile),
        "TEMP": str(workspace), "TMP": str(workspace), "TMPDIR": str(workspace),
    }


def _check_derivative(path: Path, conversion: dict) -> None:
    container = inspect_glb(path)
    with path.open("rb") as source:
        source.seek(12)
        length = struct.unpack("<I", source.read(4))[0]
        source.seek(20)
        document = json.loads(source.read(length))
    materials = {material.get("name"): material for material in document.get("materials", [])}
    expected = conversion["material_texture_channels"]
    if set(materials) != set(expected):
        raise ValueError("GLB export changed the selected materials")
    for name, channels in expected.items():
        material = materials[name]
        texture_info = material | material.get("pbrMetallicRoughness", {})
        if not set(channels) <= texture_info.keys():
            raise ValueError(f"GLB export did not preserve the supported texture channels in {name!r}")
    conversion["derivative_texture_count"] = container["texture_count"]


def import_blendkit(source: Path, asset_id: str, provenance: Provenance, registry: AssetRegistry, *,
                    provider_asset_id: str, plan: str, objects: tuple[str, ...] = (),
                    collections: tuple[str, ...] = (), blender: Path | None = None, timeout: int = 120) -> dict:
    """Convert, validate and register a private derivative of user-reviewed native data."""
    ID.validate_python(asset_id)
    if not asset_id.startswith("blendkit-") or asset_id == "blendkit-":
        raise ValueError("Blendkit import requires a local asset ID with a blendkit- prefix")
    provenance = Provenance.model_validate(provenance.model_dump())
    provider_asset_id = _require_approval(provider_asset_id, plan, provenance)
    selection = _selection(objects, collections)
    if type(timeout) is not int or not 1 <= timeout <= 600:
        raise ValueError("Native conversion and inspection timeout must be between 1 and 600 seconds each")
    root = contained_path(registry.root, "blendkit-private")
    root.mkdir(mode=0o700, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="work-", dir=root) as directory:
        workspace = Path(directory)
        native, derivative, output = (workspace / name for name in ("source.blend", "asset.glb", "conversion.json"))
        source_hash = _snapshot(Path(source), native)
        _check_container(native)
        settings = workspace / "selection.json"
        atomic_json(settings, {"selection": selection, "provider_asset_id": provider_asset_id})
        worker = Path(__file__).resolve().parents[1] / "adapters" / "blender" / "convert_native.py"
        executable = find_tool("blender", blender)
        log = workspace / "blender.log"
        try:
            elapsed = run_logged([str(executable), "--background", "--factory-startup", "--disable-autoexec",
                                  "--offline-mode", "--threads", "2", "--python-exit-code", "1", "--python",
                                  str(worker), "--", str(native), str(derivative), str(settings), str(output)],
                                 log, timeout, env=_isolated_environment(workspace))
        except RuntimeError as exc:
            if output.is_file() and output.stat().st_size <= 64 * 1024:
                failure = json.loads(output.read_text(encoding="utf-8")).get("error")
                if failure:
                    raise ValueError(f"Native asset rejected: {failure}") from exc
            raise RuntimeError(f"Native conversion did not complete with Blender: {str(exc).split(';')[0]}") from exc
        conversion = json.loads(output.read_text(encoding="utf-8"))
        conversion.update(profile=PROFILE, process_seconds=elapsed, selection=selection)
        _check_derivative(derivative, conversion)

        if file_hash(native) != source_hash:
            raise ValueError("Native source snapshot changed during conversion")
        size = native.stat().st_size
        original = contained_path(root, f"sources/{source_hash}.blend")
        original.parent.mkdir(exist_ok=True)
        if original.exists():
            if not original.is_file() or file_hash(original) != source_hash:
                raise ValueError("Blendkit native source cache has a content hash mismatch")
        else:
            os.replace(native, original)

        asset = registry.register(derivative, asset_id, provenance)
        receipt_key = f"{asset_id}:{asset['version']}:{provider_asset_id}:{source_hash}".encode()
        receipt_hash = hashlib.sha256(receipt_key + settings.read_bytes()).hexdigest()
        receipt_path = contained_path(root, f"receipts/{receipt_hash}.json")
        receipt = {"provider": "blendkit", "provider_asset_id": provider_asset_id, "plan": plan,
                   "acquisition_mode": "user-mediated", "review_basis": "operator-declaration",
                   "license_url": LICENSE_URL, "terms_url": TERMS_URL, "source_format": "blend",
                   "source": {"sha256": source_hash, "size_bytes": size,
                              "file": original.relative_to(registry.root).as_posix(), "url": provenance.source_url},
                   "conversion": conversion, "asset": asset, "recorded_at": utc_now()}
        try:
            if asset["inspection"]["status"] != "ready":
                inspect_asset(registry, asset_id, asset["version"], blender=executable, timeout=timeout)
            registry.resolve(asset_id, asset["version"])
        finally:
            receipt["asset"] = registry.get(asset_id, asset["version"])
            receipt["receipt_file"] = receipt_path.relative_to(registry.root).as_posix()
            atomic_json(receipt_path, receipt)
        return receipt
