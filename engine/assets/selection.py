"""Join source metadata and measured registry evidence for a reproducible shortlist."""
import hashlib
import re
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import Field, StrictInt

from engine.assets.providers import search_catalog
from engine.assets.registry import AssetRegistry
from engine.core.models import Model
from engine.storage.jobs import contained_path


SearchTerm = Annotated[str, Field(min_length=1, max_length=100)]
QUALITY = {"unverified": 0, "basic": 1, "standard": 2, "high": 3}
OPEN_LICENSES = {"CC0-1.0", "CC-BY-4.0", "LicenseRef-ATLAS-Generated"}
PROVIDER_HOSTS = {"polyhaven.com": "polyhaven", "sketchfab.com": "sketchfab", "www.blendkit.com": "blendkit",
                  "blendkit.com": "blendkit", "3d.si.edu": "smithsonian", "ambientcg.com": "ambientcg"}


class AssetRequirements(Model):
    query: Annotated[str, Field(max_length=500)] = ""
    category: SearchTerm | None = None
    subcategory: SearchTerm | None = None
    historical_period: SearchTerm | None = None
    cultural_setting: SearchTerm | None = None
    style: SearchTerm | None = None
    commercial_use_required: bool = True
    require_ready: bool = True
    minimum_quality: Literal["basic", "standard", "high"] = "basic"
    max_polygons: Annotated[StrictInt, Field(ge=1, le=20_000_000)] | None = None
    max_texture_size: Literal[1024, 2048, 4096, 8192] | None = None
    max_local_bytes: Annotated[StrictInt, Field(ge=1)] | None = None
    needs_rig: bool = False
    needs_facial_controls: bool = False
    preferred_providers: list[SearchTerm] = Field(default_factory=list, max_length=20)


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[^\W_]+", value.casefold()))


def _local_view(entry):
    meta = entry["provenance"]
    provider = PROVIDER_HOSTS.get(urlsplit(meta["source_url"]).hostname, entry["id"].partition("-")[0])
    return {"id": entry["id"], "provider": provider, "name": meta["name"], "tags": meta["tags"],
            "category": meta["category"], "description": meta["description"], "license_id": meta["license_id"],
            "source_url": meta["source_url"], "creator": meta["creator"],
            "style": "photorealistic" if provider == "polyhaven" or "realistic" in meta["tags"] else
            "stylized-low-poly" if provider == "kaykit" else "unclassified"}


def _grade(proof):
    if not proof:
        return "unverified"
    if not proof.get("textures"):
        return "basic"
    channels = {channel for group in proof.get("surface_channels", {}).values() for channel in group}
    largest = max(max(image["size"]) for image in proof["textures"])
    return "high" if largest >= 1024 and {"Base Color", "Normal"} <= channels else "standard"


def select_assets(requirement: AssetRequirements, cache: Path, library: Path, *, seed=0, limit=20) -> dict:
    if not 1 <= limit <= 100:
        raise ValueError("Select limit must be 1–100")
    sources = {}
    query = _tokens(requirement.query)
    for offset in range(0, 10_000, 1000):
        page = search_catalog(cache, " ".join(sorted(query)), limit=1000, offset=offset)
        sources.update((row["id"], row) for row in page)
        if len(page) < 1000:
            break
    registry = AssetRegistry(library) if contained_path(library, "assets.sqlite3").is_file() else None
    local_entries = {entry["id"]: entry for entry in registry.search()} if registry else {}
    for key, entry in local_entries.items():
        sources.setdefault(key, _local_view(entry))
    accepted, rejected = [], []
    for key, row in sources.items():
        entry = local_entries.get(key)
        rights = entry["provenance"] if entry else row
        if entry and row.get("source_url") != rights["source_url"]:
            row = _local_view(entry)
        tags = sorted(set(row.get("tags", [])) | set(rights.get("tags", [])))
        review_tags = rights.get("tags", []) if entry else []
        category_path = row.get("category_path") or ""
        metadata = _tokens(" ".join([key, row["name"], row.get("description") or "", category_path, *tags]))
        if not query <= metadata:
            continue
        provider, style = row["provider"], row.get("style", "unclassified")
        reasons = []
        categories = {part.strip().casefold() for part in (row["category"] + "/" + category_path).split("/")}
        if requirement.category and requirement.category.casefold() not in categories:
            reasons.append("category")
        if requirement.subcategory and not _tokens(requirement.subcategory) <= metadata:
            reasons.append("subcategory")
        if requirement.style and not (requirement.style.casefold() == style or
                                      requirement.style.casefold() == "realistic" and style == "photorealistic"):
            reasons.append("style")
        if requirement.historical_period and f"period:{requirement.historical_period.casefold()}" not in review_tags:
            reasons.append("history")
        if requirement.cultural_setting and f"culture:{requirement.cultural_setting.casefold()}" not in review_tags:
            reasons.append("culture")
        status, proof, pin = "discovered", None, None
        if entry:
            status = entry["inspection"]["status"]
            if status == "pending":
                status = "registered"
            if status == "ready" and not reasons:
                try:
                    resolved = registry.resolve(key, entry["version"])
                    proof = resolved["inspection"]["report"]
                    pin = {"id": key, "version": entry["version"], "sha256": entry["sha256"]}
                except (OSError, ValueError):
                    status = "invalid-local-content"
            elif status == "ready":
                status = "unverified-local"
        if requirement.require_ready and status != "ready":
            reasons.append("inspection")
        if requirement.commercial_use_required and (rights.get("license_id") not in OPEN_LICENSES or
                entry is not None and (rights["approval"] != "approved" or not rights["render_allowed"])):
            reasons.append("commercial-license")
        quality = _grade(proof)
        if (proof or requirement.minimum_quality != "basic") and QUALITY[quality] < QUALITY[requirement.minimum_quality]:
            reasons.append("quality")
        if requirement.max_polygons and (not proof or proof["polygon_count"] > requirement.max_polygons):
            reasons.append("polygon-budget")
        if requirement.max_texture_size:
            textures = proof.get("textures") if proof else None
            if (not proof or (textures is None and entry["container"].get("texture_count") != 0)
                    or any(max(image["size"]) > requirement.max_texture_size for image in textures or [])):
                reasons.append("texture-budget")
        if requirement.max_local_bytes and (not entry or entry["container"]["size_bytes"] > requirement.max_local_bytes):
            reasons.append("storage-budget")
        if requirement.needs_rig and (not proof or not proof.get("skeleton_count")):
            reasons.append("rig")
        if requirement.needs_facial_controls and (not proof or not proof.get("facial_shape_keys")):
            reasons.append("face")
        result = {"id": key, "provider": provider, "name": row["name"], "status": status, "style": style,
                  "quality": quality, "license_id": rights.get("license_id"), "source_url": rights.get("source_url"),
                  "category_path": category_path, "pin": pin, "polygon_count": proof["polygon_count"] if proof else None,
                  "texture_count": len(proof.get("textures", [])) if proof else None, "reasons": reasons}
        (rejected if reasons else accepted).append(result)

    def rank(item):
        providers = requirement.preferred_providers
        index = providers.index(item["provider"]) if item["provider"] in providers else len(providers)
        tie = hashlib.sha256(f"{seed}:{item['id']}".encode()).hexdigest()
        return (item["status"] != "ready", index, -QUALITY[item["quality"]], tie, item["id"])

    return {"examined": len(accepted) + len(rejected), "accepted": len(accepted), "rejected_count": len(rejected),
            "candidates": sorted(accepted, key=rank)[:limit], "rejected": sorted(rejected, key=rank)[:limit]}
