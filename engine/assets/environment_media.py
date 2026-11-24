"""Resolve approved source media and copy verified files into the production job."""
import hashlib
import json
from pathlib import Path
import re
import shutil

from engine.assets.registry import file_hash
from engine.storage.jobs import atomic_json, contained_path

CHANNELS = {"hdri": {"hdri": ".hdr"}, "material": {"Diffuse": ".jpg", "Rough": ".jpg", "nor_gl": ".jpg"}}


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
            if (origin["id"] != reference.id or origin["provider"] != "polyhaven"
                    or origin["license_id"] != "CC0-1.0" or not record["license_text"]
                    or origin["category"] != category or reference.fingerprint != media_fingerprint(record)):
                raise ValueError(f"Environment media identity or fingerprint mismatch: {reference.id}")
            if sorted(f["channel"] for f in record["files"]) != sorted(CHANNELS[category]):
                raise ValueError(f"Environment media channel mismatch: {reference.id}")
            for item in record["files"]:
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
            relative = f"environment/{digest}{CHANNELS[category][channel]}"
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
