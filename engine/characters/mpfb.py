"""Pinned MakeHuman Community runtime and reusable character generation."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Literal
from zipfile import ZipFile

from engine.assets.acquisition import MIB, download, fetch_bytes, unpack_models
from engine.assets.inspection import inspect_asset
from engine.assets.models import Provenance
from engine.assets.registry import AssetRegistry, file_hash
from engine.core.models import Identifier, Model, Unit
from engine.rendering.runtime import capture, find_tool, run_logged
from engine.storage.jobs import atomic_json, contained_path

REVISION = "d0a32e57a7f915cb2f2b95410e2117648c7bbb7e"
SOURCE_URL = f"https://github.com/makehumancommunity/mpfb2/tree/{REVISION}"
SOURCE_ZIP = f"https://codeload.github.com/makehumancommunity/mpfb2/zip/{REVISION}"
SOURCE_HASH = "b50c69cea33cce250ca49d838079904da7fb84a21943f3cb7fc5a9bb3e0165f8"
PACKS = {
    "asset_packs/makehuman_system_assets/makehuman_system_assets_cc0.zip":
        (280737770, "b542127a8e25547c7c29c19f2d1d2adb9a664c80396ecd694095dbc8028a0107"),
    "functional/visemes02.zip": (130733, "a69ab6fb95ddd5f56f70acc7e859f5f9c6ae613c527d577ea1571eff2183d29e"),
    "functional/faceunits01.zip": (257821, "d113107bd7eb59f3af4df6fc0ec29bfcc593f496d0b336aec14f086a80ce7146"),
}


class HumanSpec(Model):
    id: Identifier
    seed: int = 1
    age: Unit = .5
    build: Unit = .5
    muscularity: Unit = .5
    height: Unit = .5
    proportions: Unit = .5
    gender: Unit = .85
    ancestry: Literal["mixed", "african", "asian", "caucasian"] = "mixed"
    hair: Literal["short01", "short02", "bob01", "braid01", "afro01"] = "short01"
    skin: Literal["young_caucasian_male", "middleage_caucasian_male", "middleage_african_male",
                  "old_asian_male", "young_asian_female", "middleage_african_female"] = "middleage_caucasian_male"
    wardrobe: Literal["casual", "formal", "worker", "casual-female", "formal-female"] = "casual"


def _expand(archive: Path, target: Path, *, prefix: str | None = None):
    with ZipFile(archive) as packed:
        files = unpack_models(packed, allow_scripts=prefix is not None)
        for name, member in files.items():
            if prefix is not None:
                if not name.startswith(prefix):
                    continue
                name = name.removeprefix(prefix)
            destination = contained_path(target, name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(packed.read(member))


def _pinned(cache: Path, url: str, size: int, digest: str):
    blob = contained_path(cache, f"blobs/{digest}")
    if blob.is_file() and blob.stat().st_size == size and file_hash(blob) == digest:
        return blob, {"url": url, "bytes": size, "sha256": digest, "cache_hit": True}
    blob, evidence = download(url, cache, size, expected_size=size)
    if evidence["sha256"] != digest:
        raise ValueError(f"MPFB source archive SHA256 mismatch: {url}")
    return blob, evidence


def install_runtime(root: Path, *, blender: Path | None = None) -> dict:
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    executable = str(find_tool("blender", blender))
    source, source_log = _pinned(root / "cache", SOURCE_ZIP, 45813741, SOURCE_HASH)
    resources = root / "profile"
    environment = os.environ | {"BLENDER_USER_RESOURCES": str(resources)}
    with tempfile.TemporaryDirectory(prefix="mpfb-source-", dir=root) as directory:
        stage = Path(directory)
        _expand(source, stage, prefix=f"mpfb2-{REVISION}/src/mpfb/")
        run_logged([executable, "--command", "extension", "build", "--source-dir", str(stage),
                    "--output-dir", str(root)], root / "build.log", 120, env=environment)
    run_logged([executable, "--command", "extension", "install-file", "-r", "user_default",
                str(root / "mpfb-2.0.18.zip")], root / "install.log", 120, env=environment)
    data = contained_path(resources, "extensions/.user/user_default/mpfb/data")
    records = []
    for name, (size, digest) in PACKS.items():
        url = f"https://files.makehumancommunity.org/{name}"
        archive, record = _pinned(root / "cache", url, size, digest)
        _expand(archive, data)
        records.append(record)
    license_text = fetch_bytes(f"https://raw.githubusercontent.com/makehumancommunity/mpfb2/{REVISION}/LICENSE.ASSETS.md").decode()
    value = {"revision": REVISION, "version": "2.0.18", "sources": [source_log, *records], "license_text": license_text}
    atomic_json(root / "runtime.json", value)
    return value


def _cached_take(output: Path, identity: dict):
    try:
        pointer = json.loads((output / "current.json").read_text(encoding="utf-8"))
        take = contained_path(output, pointer["take"])
        report = json.loads((take / "generation.json").read_text(encoding="utf-8"))
        if any(report.get(key) != value for key, value in identity.items()):
            return None
        if report["sha256"] != file_hash(take / "human.glb"):
            return None
        if report["source_blend_sha256"] != file_hash(take / "source.blend"):
            return None
        return take, report
    except (OSError, KeyError, TypeError, ValueError):
        return None


def generate(spec: HumanSpec, runtime: Path, library: Path, *, blender: Path | None = None) -> dict:
    started = time.perf_counter()
    runtime = runtime.resolve()
    descriptor = runtime / "runtime.json"
    if not descriptor.is_file():
        raise ValueError("Install the pinned MPFB runtime with characters install-mpfb first")
    installer = json.loads(descriptor.read_text(encoding="utf-8"))
    if installer.get("revision") != REVISION or not installer.get("license_text"):
        raise ValueError("MPFB runtime does not match the pinned revision")
    executable = find_tool("blender", blender)
    blender_build = capture([str(executable), "--version"]).splitlines()[0]
    worker = Path(__file__).resolve().parents[1] / "adapters" / "blender" / "generate_human.py"
    identity = {"profile": "atlas-mpfb-human-1", "spec": spec.model_dump(mode="json"),
                "revision": REVISION, "source_archives": [SOURCE_HASH, *(item[1] for item in PACKS.values())],
                "worker_sha256": file_hash(worker), "controls_sha256": file_hash(worker.with_name("human_controls.py")),
                "blender_build": blender_build}
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    output = contained_path(runtime, f"generated/{key}")
    output.mkdir(parents=True, exist_ok=True)
    cached = _cached_take(output, identity)
    if cached is not None:
        take, report = cached
    else:
        # Concurrent invocations write independent files. Only completed takes are published.
        take = Path(tempfile.mkdtemp(prefix="take-", dir=output))
        atomic_json(take / "spec.json", spec.model_dump(mode="json"))
        elapsed = run_logged([str(executable), "--background", "--factory-startup", "--disable-autoexec",
            "--threads", "4", "--python-exit-code", "1", "--python", str(worker), "--", str(take)],
            take / "blender.log", 300, env=os.environ | {"BLENDER_USER_RESOURCES": str(runtime / "profile")})
        details = json.loads((take / "worker.json").read_text(encoding="utf-8"))
        report = identity | details | {"sha256": file_hash(take / "human.glb"),
            "source_blend_sha256": file_hash(take / "source.blend"), "generation_process_seconds": elapsed}
        atomic_json(take / "generation.json", report)
    character = take / "human.glb"
    provenance = Provenance(name=spec.id, creator="MakeHuman Community and Mika Suominen, generated locally by ATLAS",
        source_url=SOURCE_URL, license_id="CC0-1.0", license_text=installer["license_text"], approval="approved",
        render_allowed=True, redistribution_allowed=True, category="character", tags=["realistic", "mpfb", spec.wardrobe],
        description=json.dumps(identity, sort_keys=True))
    registry = AssetRegistry(library)
    entry = registry.register(character, spec.id, provenance, profile="human")
    if entry["inspection"]["status"] != "ready":
        inspect_asset(registry, spec.id, entry["version"], blender=executable)
    entry = registry.resolve(spec.id, entry["version"])
    if cached is None:
        atomic_json(output / "current.json", {"take": take.name})
    return {"id": spec.id, "version": entry["version"], "sha256": entry["sha256"], "generation": report,
            "cache_hit": cached is not None, "seconds": time.perf_counter() - started,
            "inspection": entry["inspection"]["report"], "artifact": str(character)}
