"""Versioned motion bakes backed by approved registry assets and content hashes."""
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import shutil
import tempfile

from engine.adapters.blender.retarget_anatomy import MAPPING_VERSION
from engine.assets.registry import AssetRegistry, file_hash
from engine.characters.cmu import CMU_MIRROR, CMU_TERMS, reviewed_capture
from engine.rendering.runtime import capture, find_tool, run_logged
from engine.storage.jobs import atomic_json, contained_path


PROFILE = "atlas-motion-2"
LEGACY_PROFILE = "atlas-motion-1"
RETARGET_VERSION = "anatomical-frame-1"
MAX_BYTES = 24 * 1024 * 1024
ID = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}")
HASH = re.compile(r"[a-f0-9]{64}")


def store_motion(root, identifier, content):
    if not ID.fullmatch(identifier):
        raise ValueError("Invalid motion ID")
    body = (json.dumps(content, indent=2, allow_nan=False) + "\n").encode()
    if len(body) > MAX_BYTES:
        raise ValueError("Motion bake exceeds 24 MiB")
    digest = hashlib.sha256(body).hexdigest()
    blob = contained_path(root, f"blobs/{digest}.json")
    if not blob.is_file() or file_hash(blob) != digest:
        blob.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=blob.parent, delete=False) as output:
            temporary = Path(output.name)
            output.write(body)
        try:
            os.replace(temporary, blob)
        finally:
            temporary.unlink(missing_ok=True)
    pin = {"id": identifier, "sha256": digest}
    atomic_json(contained_path(root, f"motions/{identifier}/{digest}.json"), pin)
    return pin


def load_motion(root, pin):
    identifier, digest = pin["id"], pin["sha256"]
    if not ID.fullmatch(identifier) or not HASH.fullmatch(digest):
        raise ValueError("Invalid motion pin")
    alias = contained_path(root, f"motions/{identifier}/{digest}.json")
    blob = contained_path(root, f"blobs/{digest}.json")
    if not alias.is_file() or not blob.is_file():
        raise ValueError(f"Pinned motion {identifier} is missing from the motion cache")
    if blob.stat().st_size > MAX_BYTES or file_hash(blob) != digest:
        raise ValueError(f"Pinned motion {identifier} has an invalid size or hash")
    if alias.stat().st_size > 1024 or json.loads(alias.read_text(encoding="utf-8")) != pin:
        raise ValueError(f"Pinned motion {identifier} has an invalid registry record")
    record = json.loads(blob.read_text(encoding="utf-8"))
    if record.get("profile") not in {LEGACY_PROFILE, PROFILE}:
        raise ValueError("Unsupported motion profile")
    return record, blob


def motions(root, *, include_legacy=False):
    directory = contained_path(root, "motions")
    for alias in sorted(directory.glob("*/*.json")):
        pin = {"id": alias.parent.name, "sha256": alias.stem}
        record, _ = load_motion(root, pin)
        if include_legacy or record["profile"] == PROFILE:
            yield summarize(pin, record)


def summarize(pin, record):
    bake = record["bake"]
    return {"motion": pin, "profile": record["profile"], "legacy": record["profile"] == LEGACY_PROFILE,
            "settings": record.get("settings", {}), **{key: record[key] for key in ("source", "target", "category")},
            "fps": bake["fps"], "frames": len(bake["frames"]),
            "duration_seconds": (len(bake["frames"]) - 1) / bake["fps"], "metrics": bake["metrics"]}


def retarget(source_id, clip, target_id, identifier, source_library, library, cache, *, source_version=1,
             target_version=1, category="walk", ground=True, refinement="category", blender=None):
    if not ID.fullmatch(identifier) or category not in {"idle", "walk", "run", "sit", "gesture"}:
        raise ValueError("Choose a valid motion ID and category")
    if refinement not in {"category", "none"}:
        raise ValueError("Choose category refinement or the unrefined transfer")
    source = AssetRegistry(source_library).resolve(source_id, source_version)
    target = AssetRegistry(library).resolve(target_id, target_version)
    sr, tr = (entry["inspection"]["report"] for entry in (source, target))
    if (source["container"].get("profile") != "rigged" or not source_id.startswith("kaykit-")
            or source["provenance"]["license_id"] != "CC0-1.0" or sr["humanoid_mapping"].get("pelvis") != "hips"
            or target["container"].get("profile") != "human" or tr["humanoid_mapping"].get("pelvis") != "pelvis"):
        raise ValueError("Retargeting requires an approved KayKit source and an inspected MPFB target")
    source_clip = next((row for row in sr["clips"] if row["name"] == clip), None)
    if not source_clip or source_clip["duration_seconds"] > 12:
        raise ValueError("Choose an inspected source clip of at most 12 seconds")
    if ground and category not in {"walk", "run", "idle"}:
        raise ValueError("Shoe grounding is supported for flat locomotion and idle")
    provenance = source["provenance"]
    clip_fingerprint = hashlib.sha256(json.dumps({"asset": source["sha256"], "clip": source_clip},
                                                sort_keys=True).encode()).hexdigest()
    metadata = {"profile": PROFILE, "category": category,
                "source": {"id": source_id, "version": source_version, "sha256": source["sha256"],
                           "clip": clip, "clip_sha256": clip_fingerprint,
                           "skeleton_sha256": sr["skeleton_sha256"], "family": "kaykit",
                           "source_url": provenance["source_url"], "creator": provenance["creator"],
                           "license_id": provenance["license_id"], "frames": source_clip["frames"]},
                "target": {"id": target_id, "version": target_version, "sha256": target["sha256"],
                           "skeleton_sha256": tr["skeleton_sha256"], "family": "mpfb-game-engine"},
                "settings": {"ground": ground, "refinement": refinement}}
    request = {"source": str(source["path"]), "target": str(target["path"]), "clip": source_clip,
               "ground": ground, "category": category, "refinement": refinement}
    return _bake_cached(identifier, metadata, request, cache, blender)


def retarget_cmu(path, target_id, identifier, library, cache, *, target_version=1, blender=None):
    if not ID.fullmatch(identifier):
        raise ValueError("Choose a valid motion ID")
    digest, (clip, category, subject) = reviewed_capture(path)
    target = AssetRegistry(library).resolve(target_id, target_version)
    tr = target["inspection"]["report"]
    if target["container"].get("profile") != "human" or tr["humanoid_mapping"].get("pelvis") != "pelvis":
        raise ValueError("CMU retargeting requires an inspected MPFB target")
    hierarchy = path.read_bytes().partition(b"MOTION")[0]
    metadata = {"profile": PROFILE, "category": category, "source": {
        "id": f"cmu-{clip}", "version": 1, "sha256": digest, "clip": clip, "clip_sha256": digest,
        "skeleton_sha256": hashlib.sha256(hierarchy).hexdigest(), "family": "cmu-motionbuilder-bvh",
        "source_url": f"{CMU_MIRROR}/data/{subject}/{clip}.bvh", "terms_url": CMU_TERMS,
        "creator": "CMU Graphics Lab, BVH conversion by Bruce Hahne", "license_id": "LicenseRef-CMU-Mocap",
        "attribution": ("The data used in this project was obtained from mocap.cs.cmu.edu. "
                        "The database was created with funding from NSF EIA-0196217."),
        "restrictions": ["No direct resale, including converted data"]},
        "target": {"id": target_id, "version": target_version, "sha256": target["sha256"],
                   "skeleton_sha256": tr["skeleton_sha256"], "family": "mpfb-game-engine"},
        "settings": {"ground": category == "walk", "refinement": "none", "format": "bvh", "mapping": "cmu-mpfb-anatomy-1"}}
    request = {"source": str(path.resolve()), "target": str(target["path"]), "source_format": "cmu-bvh",
               "source_sha256": digest, "ground": category == "walk", "category": category, "refinement": "none"}
    return _bake_cached(identifier, metadata, request, cache, blender)


def _bake_cached(identifier, metadata, request, cache, blender):
    executable = str(find_tool("blender", blender))
    worker = Path(__file__).resolve().parents[1] / "adapters/blender/bake_motion.py"
    metadata["settings"].setdefault("mapping", MAPPING_VERSION)
    metadata["settings"].update(fps=30, algorithm=RETARGET_VERSION,
        worker_sha256=file_hash(worker), anatomy_sha256=file_hash(worker.with_name("retarget_anatomy.py")),
        importer_sha256=file_hash(worker.with_name("asset_import.py")),
        skeleton_worker_sha256=file_hash(worker.with_name("skeleton.py")),
        blender=capture([executable, "--version"]).splitlines()[:7])
    key = hashlib.sha256(json.dumps(metadata, sort_keys=True).encode()).hexdigest()
    pointer = contained_path(cache, f"bakes/{key}.json")
    if pointer.is_file():
        try:
            cached, _ = load_motion(cache, json.loads(pointer.read_text(encoding="utf-8")))
            if all(cached.get(name) == value for name, value in metadata.items()):
                pin = store_motion(cache, identifier, cached)
                return summarize(pin, cached) | {"cache_hit": True}
        except (OSError, ValueError, KeyError, TypeError):
            pass
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="bake-", dir=cache) as temporary:
        directory = Path(temporary)
        if request.get("source_format") == "cmu-bvh":
            snapshot = directory / "source.bvh"
            shutil.copyfile(request["source"], snapshot)
            if file_hash(snapshot) != request["source_sha256"]:
                raise ValueError("Reviewed CMU capture changed during snapshot preparation")
            request = request | {"source": str(snapshot.resolve())}
        atomic_json(directory / "request.json", request)
        elapsed = run_logged([executable, "--background", "--factory-startup", "--disable-autoexec", "--offline-mode",
            "--threads", "4", "--python-exit-code", "1", "--python", str(worker), "--", str(directory)],
            _init_log(cache, key), 180)
        bake = json.loads((directory / "bake.json").read_text(encoding="utf-8"))
    record = metadata | {"bake": bake}
    pin = store_motion(cache, identifier, record)
    atomic_json(pointer, pin)
    return summarize(pin, record) | {"cache_hit": False, "process_seconds": elapsed}


def _init_log(cache, key):
    path = contained_path(cache, f"logs/{key}.log")
    path.parent.mkdir(exist_ok=True)
    return path


def resolve_motions(project, cache):
    pins = [action.motion for action in project.actions]
    pins.extend(clip.motion for actor in project.scene.entities for clip in getattr(actor, "clips", ()) if clip.motion)
    resolved = {}
    for identifier, digest in sorted({(pin.id, pin.sha256) for pin in pins}):
        pin = {"id": identifier, "sha256": digest}
        record, source = load_motion(cache, pin)
        if record["profile"] == LEGACY_PROFILE:
            logging.getLogger("atlas").warning(f"Project explicitly pins legacy bake {identifier}@{digest}. Rebake for corrected anatomy.")
        resolved[identifier, digest] = (pin, record, source)
    return resolved


def snapshot_motions(resolved, directory):
    if not resolved:
        return []
    manifest = []
    mapping = {}
    for (_, digest), (pin, record, source) in resolved.items():
        relative = f"motions/{digest}.json"
        entry = summarize(pin, record) | {"source_file": relative}
        if digest not in mapping:
            destination = contained_path(directory, relative)
            destination.parent.mkdir(exist_ok=True)
            shutil.copyfile(source, destination)
            if file_hash(destination) != digest:
                raise ValueError("Motion content changed during the render snapshot")
            mapping[digest] = entry | {"aliases": []}
        mapping[digest]["aliases"].append(pin["id"])
        manifest.append(entry)
    atomic_json(directory / "motion-map.json", mapping)
    return manifest
