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
    human_faces = {p.actor_id for p in project.performances if p.profile == "mpfb-visemes-1"}
    for entity in [*project.scene.entities, *(group.prototype for group in project.scene.scatter)]:
        if not isinstance(entity, AssetEntity):
            continue
        entry = pinned[(entity.asset.id, entity.asset.version)]
        rigged = isinstance(entity, RiggedEntity)
        profile = entry["container"].get("profile", "static")
        if rigged != (profile in {"rigged", "human"}):
            raise ValueError(f"Asset profile does not match entity {entity.id}")
        if profile == "human" and project.schema_version != "1.4":
            raise ValueError("MPFB humans require schema 1.4")
        if entity.id in human_faces and profile != "human":
            raise ValueError(f"Actor {entity.id} has no inspected MPFB human facial profile")
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


def write_video_credits(directory: Path, models: list[dict], media: list[dict]) -> None:
    license_urls = {"CC0-1.0": "https://creativecommons.org/publicdomain/zero/1.0/",
                    "CC-BY-4.0": "https://creativecommons.org/licenses/by/4.0/"}
    lines = []
    for record in [*(entry["provenance"] for entry in models), *(entry["catalog"] for entry in media)]:
        license_id = record["license_id"]
        license_url = license_urls.get(license_id)
        credit = record.get("attribution") or record.get("credit")
        name = record.get("name") or record.get("id") or "Asset"
        creator = record.get("creator")
        fields = [f"{name} by {creator}" if creator else name]
        if record.get("source_url"):
            fields.append(record["source_url"])
        fields.append(f"{license_id} {license_url}" if license_url else license_id)
        if credit:
            fields.append(credit)
        lines.append(" | ".join(" ".join(item.split()) for item in fields))
    if lines:
        (directory / "video-credits.txt").write_text("\n".join(dict.fromkeys(lines)) + "\n", encoding="utf-8")
