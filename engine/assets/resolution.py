"""Resolve portable references to approved, immutable production snapshots."""
import shutil
from pathlib import Path

from engine.assets.registry import AssetRegistry, file_hash
from engine.core.models import AssetEntity, Project, RiggedEntity
from engine.storage.jobs import atomic_json, contained_path


def project_asset_references(project: Project) -> list[tuple[str, int]]:
    entities = [*project.scene.entities, *(group.prototype for group in project.scene.scatter)]
    return sorted({(entity.asset.id, entity.asset.version) for entity in entities if isinstance(entity, AssetEntity)})


def resolve_project_assets(project: Project, library: Path) -> list[dict]:
    references = project_asset_references(project)
    if not references:
        return []
    if not contained_path(library, "assets.sqlite3").is_file():
        raise ValueError(f"Asset library does not exist: {library}. Register and inspect the referenced assets first.")
    registry = AssetRegistry(library)
    entries = [registry.resolve(asset_id, version) for asset_id, version in references]
    pinned = {(entry["id"], entry["version"]): entry for entry in entries}
    for entity in [*project.scene.entities, *(group.prototype for group in project.scene.scatter)]:
        if not isinstance(entity, AssetEntity):
            continue
        entry = pinned[(entity.asset.id, entity.asset.version)]
        rigged = isinstance(entity, RiggedEntity)
        if rigged != (entry["container"].get("profile", "static") == "rigged"):
            raise ValueError(f"Asset profile does not match entity {entity.id}")
        if rigged:
            report = entry["inspection"]["report"]
            if any(role not in report["humanoid_mapping"] for role in entity.equipment):
                raise ValueError(f"Equipment bone role is unavailable on {entity.id}")
            clips = {clip["name"]: clip for clip in report["clips"]}
            for event in entity.clips:
                clip = clips.get(event.name)
                if clip is None:
                    raise ValueError(f"Unknown clip {event.name} for pinned actor {entity.id}")
                duration = event.frame_count / project.render.fps * event.speed
                if not event.loop and duration > clip["duration_seconds"] + 1e-6:
                    raise ValueError(f"Nonlooping clip {event.name} exceeds its source duration")
                if event.loop and duration / clip["duration_seconds"] > 1000:
                    raise ValueError(f"Clip {event.name} exceeds Blender's 1000-repeat limit")
    return entries


def snapshot_assets(entries: list[dict], directory: Path) -> list[dict]:
    """Copy once per content hash, retain separate provenance for each reference."""
    snapshots = []
    for entry in entries:
        relative = f"assets/{entry['sha256']}.glb"
        destination = contained_path(directory, relative)
        destination.parent.mkdir(exist_ok=True)
        if not destination.exists():
            shutil.copyfile(entry["path"], destination)
        if file_hash(destination) != entry["sha256"]:
            raise ValueError("Asset content hash changed while preparing the render snapshot")
        snapshots.append({key: value for key, value in entry.items() if key != "path"} | {"source_file": relative})
    atomic_json(directory / "asset-map.json", {f"{entry['id']}@{entry['version']}": entry for entry in snapshots})
    if snapshots:
        notices = []
        for entry in snapshots:
            meta = entry["provenance"]
            notices.append(f"{meta['name']} — {meta['creator']}\nSource: {meta['source_url']}\n"
                           f"License: {meta['license_id']}\nAttribution: {meta['attribution'] or '(none declared)'}\n")
        (directory / "attributions.txt").write_text("\n".join(notices), encoding="utf-8")
    return snapshots
