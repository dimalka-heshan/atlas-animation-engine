"""Official provider adapters and an offline-searchable local source catalog."""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import tempfile
from typing import Protocol
from zipfile import BadZipFile, ZipFile

from engine.assets.acquisition import MIB, archive_model, download, fetch_bytes, unpack_models
from engine.assets.environment_media import media_fingerprint
from engine.assets.models import Provenance
from engine.assets.registry import AssetRegistry
from engine.storage.jobs import atomic_json, contained_path, utc_now


class Provider(Protocol):
    id: str
    label: str
    def discover(self) -> list[dict]: ...
    def acquire(self, entry: dict, cache: Path, library: Path, budget: int) -> dict: ...


PACKS = {
    "adventurers": ("KayKit-Character-Pack-Adventures-1.0", "672074b73ba276876a19e8816ecdc5241817ab47"),
    "medieval": ("KayKit-Medieval-Hexagon-Pack-1.0", "84fa4e91af6a88989be7c99e0891cede11f2ca38"),
}
STARTER = {
    "fence": "buildings/neutral/fence_wood_straight.gltf",
    "gate": "buildings/neutral/wall_straight_gate.gltf",
    "wall": "buildings/neutral/wall_straight.gltf",
    "tavern": "buildings/blue/building_tavern_blue.gltf",
    "tree": "decoration/nature/tree_single_A.gltf",
    "rock": "decoration/nature/rock_single_A.gltf",
    "barrel": "decoration/props/barrel.gltf",
    "crate": "decoration/props/crate_A_big.gltf",
    "cart": "decoration/props/wheelbarrow.gltf",
    "bridge": "buildings/neutral/building_bridge_A.gltf",
}


@dataclass(frozen=True)
class KayKit:
    id: str = "kaykit"
    label: str = "KayKit official CC0 releases"

    def discover(self):
        results = []
        for pack, (repo, revision) in PACKS.items():
            base = f"{repo}-{revision}/addons/kaykit_"
            members = ({"knight": "Knight.glb", "mage": "Mage.glb"} if pack == "adventurers" else STARTER)
            for short, name in members.items():
                member = (base + "character_pack_adventures/Characters/gltf/" if pack == "adventurers"
                          else base + "medieval_hexagon_pack/Assets/gltf/") + name
                results.append({"id": f"kaykit-{short}", "provider": self.id, "pack": pack,
                    "name": f"KayKit {short.title()}", "category": "character" if pack == "adventurers" else "environment",
                    "style": "stylized-low-poly", "tags": ["medieval", pack], "creator": "Kay Lousberg",
                    "source_url": f"https://github.com/KayKit-Game-Assets/{repo}/tree/{revision}",
                    "revision": revision, "license_id": "CC0-1.0",
                    "archive_url": f"https://codeload.github.com/KayKit-Game-Assets/{repo}/zip/{revision}",
                    "license_member": base + ("character_pack_adventures" if pack == "adventurers"
                                               else "medieval_hexagon_pack") + "/LICENSE.txt", "member": member})
        return results

    def acquire(self, entry, cache, library, budget):
        # Resolve against the reviewed pinned records, even if the stored catalog was edited.
        fixed = {e["id"]: e for e in self.discover()}.get(entry["id"])
        if fixed != entry:
            raise ValueError("KayKit catalog record differs from the reviewed source revision")
        archive_path, transfer = download(entry["archive_url"], cache, budget)
        with ZipFile(archive_path) as archive:
            members = unpack_models(archive)
            if entry["license_member"] not in members or entry["member"] not in members:
                raise ValueError("Pinned release is missing the selected asset or its license")
            license_text = archive.read(members[entry["license_member"]]).decode("utf-8-sig")
            if "Creative Commons Zero" not in license_text or "creativecommons.org/publicdomain/zero/1.0" not in license_text:
                raise ValueError("Expected the pack's explicit CC0 asset license")
            member = entry["member"]
            body = archive_model(archive, members, member)
        profile = "rigged" if entry["category"] == "character" else "static"
        provenance = Provenance(name=entry["name"], creator=entry["creator"], source_url=entry["source_url"],
            license_id="CC0-1.0", license_text=license_text, approval="approved", render_allowed=True,
            redistribution_allowed=True, category=entry["category"], tags=entry["tags"],
            description=f"Official member {member}. Source ZIP SHA256 {transfer['sha256']}. Profile: {profile}.")
        with tempfile.TemporaryDirectory(prefix="atlas-asset-") as temp:
            source = Path(temp) / "asset.glb"
            source.write_bytes(body)
            record = AssetRegistry(library).register(source, entry["id"], provenance, profile=profile)
        return {"catalog": entry, "download": transfer, "asset": record}


@dataclass(frozen=True)
class PolyHaven:
    id: str = "polyhaven"
    label: str = "Powered by Poly Haven"

    def discover(self):
        results = []
        for api_type, category in [("hdris", "hdri"), ("textures", "material")]:
            data = json.loads(fetch_bytes(f"https://api.polyhaven.com/assets?t={api_type}"))
            for slug, item in sorted(data.items()):
                if not re.fullmatch(r"[a-z0-9_]{1,80}", slug):
                    continue
                results.append({"id": f"polyhaven-{slug}", "provider": self.id, "name": item["name"],
                    "slug": slug, "category": category, "style": "photorealistic",
                    "tags": sorted(set(item.get("tags", []) + item.get("categories", []))),
                    "creator": ", ".join(sorted(item.get("authors", {}))) or "Poly Haven",
                    "source_url": f"https://polyhaven.com/a/{slug}", "license_id": "CC0-1.0",
                    "revision": str(item.get("date_published", "")), "credit": self.label})
        return results

    def acquire(self, entry, cache, library, budget):
        slug = entry["slug"]
        if not re.fullmatch(r"[a-z0-9_]{1,80}", slug) or entry["id"] != f"polyhaven-{slug}":
            raise ValueError("Invalid Poly Haven asset identity")
        files = json.loads(fetch_bytes(f"https://api.polyhaven.com/files/{slug}"))
        if entry["category"] == "hdri":
            wanted = [("hdri", "hdr")]
        elif entry["category"] == "material":
            wanted = [(name, "jpg") for name in ("Diffuse", "Rough", "nor_gl")]
        else:
            raise ValueError("Unsupported Poly Haven asset category")
        try:
            sources = [(kind, files[kind]["1k"][extension]) for kind, extension in wanted]
        except (KeyError, TypeError) as exc:
            raise ValueError("Provider does not offer all requested 1k channels") from exc
        if sum(item["size"] for _, item in sources) > budget:
            raise ValueError("Selected Poly Haven files exceed the download budget")
        records = []
        for kind, item in sources:
            _, details = download(item["url"], cache, budget, expected_size=item["size"], expected_md5=item["md5"])
            records.append({"channel": kind, **details})
        text = fetch_bytes("https://creativecommons.org/publicdomain/zero/1.0/legalcode.txt", limit=MIB).decode("utf-8")
        result = {"catalog": entry, "files": records, "license_text": text, "status": "cached-source"}
        return result | {"fingerprint": media_fingerprint(result)}


PROVIDERS: dict[str, Provider] = {p.id: p for p in (KayKit(), PolyHaven())}


def synchronize(provider: str, root: Path) -> dict:
    adapter = PROVIDERS[provider]
    entries = adapter.discover()
    if len({entry["id"] for entry in entries}) != len(entries):
        raise ValueError("Provider returned duplicate catalog IDs")
    result = {"provider": provider, "credit": adapter.label, "synced_at": utc_now(), "entries": entries}
    root.mkdir(parents=True, exist_ok=True)
    with _catalog_db(root) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS catalog (
            id TEXT PRIMARY KEY, provider TEXT NOT NULL, category TEXT NOT NULL,
            style TEXT NOT NULL, text TEXT NOT NULL, record TEXT NOT NULL)""")
        db.execute("CREATE INDEX IF NOT EXISTS by_provider_category ON catalog(provider, category, id)")
        db.execute("DELETE FROM catalog WHERE provider = ?", (provider,))
        db.executemany("INSERT INTO catalog VALUES (?,?,?,?,?,?)", [
            (e["id"], provider, e["category"], e["style"],
             " ".join([e["id"], e["name"], e["category"], e["style"], *e["tags"]]).casefold(),
             json.dumps(e | {"catalog_synced_at": result["synced_at"]}, ensure_ascii=False)) for e in entries])
    return result


@contextmanager
def _catalog_db(root):
    db = sqlite3.connect(contained_path(root, "catalog.sqlite3"), timeout=30)
    try:
        with db:
            yield db
    finally:
        db.close()


def _catalog_exists(root):
    return contained_path(root, "catalog.sqlite3").is_file()


def search_catalog(root: Path, query="", *, category=None, style=None, seed=None, offset=0, limit=50) -> list[dict]:
    if offset < 0 or not 1 <= limit <= 1000:
        raise ValueError("Catalog page requires nonnegative offset and limit 1–1000")
    if len(query) > 500:
        raise ValueError("Catalog query exceeds 500 characters")
    if not _catalog_exists(root):
        return []
    where = ["instr(text, ?) > 0" for _ in query.split()]
    params = query.casefold().split()
    for column, value in (("category", category), ("style", style)):
        if value is not None:
            where.append(f"{column} = ?")
            params.append(value)
    clause = " WHERE " + " AND ".join(where) if where else ""
    with _catalog_db(root) as db:
        if seed is None:
            rows = db.execute("SELECT record FROM catalog" + clause + " ORDER BY provider,id LIMIT ? OFFSET ?",
                              (*params, limit, offset)).fetchall()
        else:
            db.create_function("seed_rank", 1, lambda value: hashlib.sha256(f"{seed}:{value}".encode()).hexdigest(),
                               deterministic=True)
            rows = db.execute("SELECT record FROM catalog" + clause + " ORDER BY seed_rank(id),id LIMIT ? OFFSET ?",
                              (*params, limit, offset)).fetchall()
    return [json.loads(row[0]) | {"catalog_match": "all query terms matched source metadata"} for row in rows]


def acquire(asset_id: str, cache: Path, library: Path, budget: int = 64 * MIB) -> dict:
    provider = asset_id.partition("-")[0]
    if provider not in PROVIDERS or not re.fullmatch(r"[a-z0-9_-]{1,100}", asset_id):
        raise ValueError("Unknown catalog asset ID")
    if not _catalog_exists(cache):
        raise ValueError(f"Synchronize {provider} before acquiring assets")
    with _catalog_db(cache) as db:
        row = db.execute("SELECT record FROM catalog WHERE id=? AND provider=?", (asset_id, provider)).fetchone()
    if row is None:
        raise ValueError(f"Asset absent from catalog: {asset_id}")
    entry = json.loads(row[0])
    entry.pop("catalog_synced_at", None)
    try:
        result = PROVIDERS[provider].acquire(entry, cache, library, budget)
    except (BadZipFile, KeyError, TypeError, UnicodeError) as exc:
        raise ValueError(f"Malformed provider asset or response: {asset_id}: {exc}") from exc
    if "fingerprint" in result:
        version = contained_path(cache, f"media-versions/{asset_id}/{result['fingerprint']}.json")
        if not version.exists():
            atomic_json(version, result)
    atomic_json(contained_path(cache, f"acquired/{asset_id}.json"), result)
    return result
