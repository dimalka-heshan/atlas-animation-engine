"""Resolve approved source media and copy verified files into the production job."""
import hashlib
import json
from pathlib import Path
import re
import shutil

from engine.assets.registry import file_hash
from engine.storage.jobs import atomic_json, contained_path

REQUIRED_CHANNELS = {"hdri": {"hdri"}, "material": {"Diffuse", "Rough", "nor_gl"}}
MATERIAL_CHANNELS = REQUIRED_CHANNELS["material"] | {"Metal", "AO", "Height", "Displacement", "Opacity", "Emission"}
MEDIA_PROVIDERS = {"hdri": {"polyhaven"}, "material": {"polyhaven", "ambientcg"}}


def media_extension(category: str, item: dict) -> str:
    extensions = {"hdr"} if category == "hdri" else {"jpg", "png"}
    default = "hdr" if category == "hdri" else "jpg"
    extension = item.get("format", default)
    if extension not in extensions:
        raise ValueError(f"Unsupported environment media format: {extension}")
    return f".{extension}"


def media_fingerprint(record: dict) -> str:
    data = {"id": record["catalog"]["id"], "category": record["catalog"]["category"],
            "files": sorted((f["channel"], f["sha256"]) for f in record["files"])}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def resolve_media(project, cache: Path) -> list[dict]:
    environment = project.scene.environment
    entries = []
    for category, reference in (("hdri", environment.hdri), ("material", environment.ground_texture)):
        if reference is None:
            continue
        path = contained_path(cache, f"media-versions/{reference.id}/{reference.fingerprint}.json")
        if not path.is_file():
            # Compatibility with caches created before immutable media history.
            path = contained_path(cache, f"acquired/{reference.id}.json")
        if not path.is_file() or path.stat().st_size > 1024 * 1024:
            raise ValueError(f"Acquire environment media {reference.id} first")
        record = json.loads(path.read_text(encoding="utf-8"))
        try:
            origin = record["catalog"]
            if (origin["id"] != reference.id or origin["provider"] not in MEDIA_PROVIDERS[category]
                    or not reference.id.startswith(origin["provider"] + "-")
                    or origin["license_id"] != "CC0-1.0" or not record["license_text"]
                    or origin["category"] != category or reference.fingerprint != media_fingerprint(record)):
                raise ValueError(f"Environment media identity or fingerprint mismatch: {reference.id}")
            channels = [item["channel"] for item in record["files"]]
            required = REQUIRED_CHANNELS[category]
            accepted = MATERIAL_CHANNELS if category == "material" else required
            if len(channels) != len(set(channels)) or not required <= set(channels) <= accepted:
                raise ValueError(f"Environment media channel mismatch: {reference.id}")
            for item in record["files"]:
                media_extension(category, item)
                digest = item["sha256"]
                if not re.fullmatch(r"[a-f0-9]{64}", digest):
                    raise ValueError("Invalid environment media hash")
                blob = contained_path(cache, f"blobs/{digest}")
                if not blob.is_file() or blob.stat().st_size != item["bytes"] or file_hash(blob) != digest:
                    raise ValueError(f"Environment media file absent or changed: {reference.id}")
        except (KeyError, TypeError) as exc:
            raise ValueError(f"Malformed environment media record: {reference.id}") from exc
        entries.append(record)
    return entries


def snapshot_media(records: list[dict], cache: Path, directory: Path) -> list[dict]:
    manifests = []
    for record in records:
        category = record["catalog"]["category"]
        snapshot = []
        for item in record["files"]:
            digest, channel = item["sha256"], item["channel"]
            # Blender reuses images by path and each channel needs its own color space.
            relative = f"environment/{digest}-{channel}{media_extension(category, item)}"
            target = contained_path(directory, relative)
            target.parent.mkdir(exist_ok=True)
            shutil.copyfile(contained_path(cache, f"blobs/{digest}"), target)
            if file_hash(target) != digest:
                raise ValueError("Environment media changed during production snapshot")
            snapshot.append(item | {"source_file": relative})
        manifests.append(record | {"files": snapshot})
    if manifests:
        atomic_json(directory / "environment-map.json", {m["catalog"]["category"]: m for m in manifests})
    return manifests
