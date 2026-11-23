"""Inspect a registered, approved GLB in an isolated Blender process."""
import json
import logging
import shutil
import uuid
from pathlib import Path

from engine.assets.registry import AssetRegistry, file_hash
from engine.rendering.runtime import find_tool, run_logged
from engine.storage.jobs import contained_path

LOG = logging.getLogger("atlas")


def inspect_asset(registry: AssetRegistry, asset_id: str, version: int, *, blender: Path | None = None,
                  timeout: int = 120) -> dict:
    registry.get(asset_id, version)
    workspace = contained_path(registry.root, f"inspections/{uuid.uuid4().hex}")
    workspace.mkdir(parents=True)
    try:
        entry = registry.resolve(asset_id, version, require_inspection=False)
        source = workspace / "source.glb"
        shutil.copyfile(entry["path"], source)
        if file_hash(source) != entry["sha256"]:
            raise ValueError("Asset content hash changed during inspection snapshot")
        worker = Path(__file__).resolve().parents[1] / "adapters" / "blender" / "inspect_asset.py"
        elapsed = run_logged([str(find_tool("blender", blender)), "--background", "--factory-startup",
            "--disable-autoexec", "--python-exit-code", "1", "--python", str(worker), "--",
            str(source), str(workspace / "report.json")], workspace / "blender.log", timeout)
        report = json.loads((workspace / "report.json").read_text(encoding="utf-8"))
        if report["missing_textures"]:
            raise ValueError(f"Asset has missing textures: {report['missing_textures']}")
        report.update(process_seconds=elapsed, source_sha256=entry["sha256"], inspection_profile="atlas-static-glb-1",
                      log=str((workspace / "blender.log").relative_to(registry.root)))
        registry.set_inspection(asset_id, version, "ready", report)
        LOG.info("asset_inspected", extra={"asset_id": asset_id, "version": version})
        return report
    except Exception as exc:
        registry.set_inspection(asset_id, version, "failed", {"error": f"{type(exc).__name__}: {exc}",
            "log": str((workspace / "blender.log").relative_to(registry.root))})
        LOG.error("asset_inspection_failed", extra={"asset_id": asset_id, "version": version, "error": str(exc)})
        raise
