"""Versioned production defaults for the existing Blender render pipeline."""
PRESETS = {
    "preview": {"engine": "eevee", "width": 480, "height": 270, "samples": 16, "look": "None"},
    "stylized": {"engine": "eevee", "width": 960, "height": 540, "samples": 48, "look": "AgX - Medium High Contrast"},
    "realistic": {"engine": "cycles", "width": 1280, "height": 720, "samples": 64, "look": "AgX - Medium High Contrast"},
    "cinematic": {"engine": "cycles", "width": 1920, "height": 1080, "samples": 128, "look": "AgX - Medium High Contrast"},
}


def enforce_geometry_budget(project, entries):
    if not project.quality:
        return
    records = {(x["id"], x["version"]): x["inspection"]["report"] for x in entries}
    total = 0
    for entity in project.scene.entities:
        if not hasattr(entity, "asset"):
            continue
        report = records[entity.asset.id, entity.asset.version]
        total += report["polygon_count"]
        if any(max(image["size"]) > project.quality.max_texture_size for image in report["textures"]):
            raise ValueError(f"Asset {entity.asset.id} exceeds the configured texture resolution budget")
    if total > project.quality.max_asset_polygons:
        raise ValueError(f"Scene has {total} imported polygons above the quality budget")
