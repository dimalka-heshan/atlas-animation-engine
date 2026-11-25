"""Official provider adapters and an offline-searchable local source catalog."""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import tempfile
from typing import Protocol
from urllib.parse import urlsplit
from zipfile import BadZipFile, ZipFile

from engine.assets.acquisition import (
    MIB, archive_model, download, fetch_bytes, pack_gltf, scale_static_glb, unpack_models,
)
from engine.assets.environment_media import media_fingerprint
from engine.assets.models import Provenance
from engine.assets.registry import AssetRegistry, file_hash
from engine.storage.jobs import atomic_json, contained_path, utc_now


class Provider(Protocol):
    id: str
    label: str
    def discover(self) -> list[dict]: ...
    def acquire(self, entry: dict, cache: Path, library: Path, budget: int, *,
                resolution: str = "1k", source_format: str | None = None) -> dict: ...


RESOLUTIONS = ("1k", "2k", "4k")
CC0 = "https://creativecommons.org/publicdomain/zero/1.0/legalcode.txt"
POLYHAVEN_FORMATS = {"hdri": "hdr", "material": "jpg", "environment": "gltf"}


def cc0_text():
    return fetch_bytes(CC0, limit=MIB).decode("utf-8")


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

    def acquire(self, entry, cache, library, budget, *, resolution="1k", source_format=None):
        if resolution != "1k" or source_format is not None:
            raise ValueError("KayKit packages have a fixed format and no selectable resolution")
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
        for api_type, category in [("hdris", "hdri"), ("textures", "material"), ("models", "environment")]:
            data = json.loads(fetch_bytes(f"https://api.polyhaven.com/assets?t={api_type}"))
            for slug, item in sorted(data.items()):
                if not re.fullmatch(r"[A-Za-z0-9_]{1,80}", slug) or (category == "environment" and len(slug) > 54):
                    continue
                results.append({"id": f"polyhaven-{slug.lower()}", "provider": self.id, "name": item["name"],
                    "slug": slug, "category": category, "style": "photorealistic",
                    "description": item.get("description", ""), "category_path": item.get("category", ""),
                    "source_attributes": item.get("attributes", {}), "thumbnail_url": item.get("thumbnail_url"),
                    "source_polygon_estimate": item.get("polycount"), "source_max_resolution": item.get("max_resolution"),
                    "source_format": POLYHAVEN_FORMATS[category], "source_files_revision": item.get("files_hash"),
                    "tags": sorted(set(item.get("tags", []) + item.get("categories", []))),
                    "creator": ", ".join(sorted(item.get("authors", {}))) or "Poly Haven",
                    "source_url": f"https://polyhaven.com/a/{slug}", "license_id": "CC0-1.0", "license_url": CC0,
                    "revision": str(item.get("date_published", "")), "credit": self.label})
        return results

    @staticmethod
    def file_index(entry):
        slug = entry["slug"]
        if not re.fullmatch(r"[A-Za-z0-9_]{1,80}", slug) or entry["id"] != f"polyhaven-{slug.lower()}":
            raise ValueError("Invalid Poly Haven asset identity")
        return json.loads(fetch_bytes(f"https://api.polyhaven.com/files/{slug}"))

    @staticmethod
    def variants(files, category):
        extension = POLYHAVEN_FORMATS[category]
        variants = []
        for resolution in RESOLUTIONS:
            try:
                if category == "environment":
                    model = files["gltf"][resolution][extension]
                    sources = [model, *model["include"].values()]
                else:
                    channels = ("hdri",) if category == "hdri" else ("Diffuse", "Rough", "nor_gl")
                    sources = [files[channel][resolution][extension] for channel in channels]
                sizes = [source["size"] for source in sources]
            except (KeyError, TypeError, AttributeError):
                continue
            if all(type(size) is int and size > 0 for size in sizes):
                variants.append({"resolution": resolution, "format": extension, "bytes": sum(sizes),
                                 "files": len(sources)})
        return variants

    @staticmethod
    def pick_variant(variants, budget, max_texture_size):
        for entry in reversed(variants):
            pixels = int(entry["resolution"].removesuffix("k")) * 1024
            if pixels <= max_texture_size and entry["bytes"] <= budget and entry["bytes"] <= 128 * MIB:
                return entry["resolution"]
        raise ValueError("No supported Poly Haven variant fits the byte budget and selected texture tier")

    def acquire(self, entry, cache, library, budget, *, resolution="1k", source_format=None, max_texture_size=4096):
        files = self.file_index(entry)
        category = entry["category"]
        if category not in POLYHAVEN_FORMATS:
            raise ValueError("Unsupported Poly Haven asset category")
        extension = POLYHAVEN_FORMATS[category]
        if source_format not in {None, extension}:
            raise ValueError(f"Poly Haven {category} supports the {extension} source format")
        if resolution == "auto":
            resolution = self.pick_variant(self.variants(files, category), budget, max_texture_size)
        if category == "environment":
            return self._acquire_model(entry, files, cache, library, budget, resolution)
        wanted = ["hdri"] if category == "hdri" else ["Diffuse", "Rough", "nor_gl"]
        try:
            sources = [(kind, files[kind][resolution][extension]) for kind in wanted]
        except (KeyError, TypeError) as exc:
            raise ValueError(f"Poly Haven does not offer all requested {resolution} channels") from exc
        downloads = self._download_files(sources, cache, budget)
        records = [details | {"channel": channel} for channel, (_, details) in downloads.items()]
        result = {"catalog": entry, "files": records, "license_text": cc0_text(), "status": "cached-source",
                  "resolution": resolution, "source_format": extension}
        return result | {"fingerprint": media_fingerprint(result)}

    @staticmethod
    def _download_files(sources, cache, budget):
        if sum(item["size"] for _, item in sources) > budget:
            raise ValueError("Selected Poly Haven files exceed the download budget")
        return {name: download(item["url"], cache, budget, expected_size=item["size"], expected_md5=item["md5"])
                for name, item in sources}

    def _acquire_model(self, entry, files, cache, library, budget, resolution):
        try:
            model = files["gltf"][resolution]["gltf"]
        except (KeyError, TypeError) as exc:
            raise ValueError(f"Poly Haven does not offer {resolution} glTF for this model") from exc
        model_name = PurePosixPath(urlsplit(model["url"]).path).name
        includes = model["include"]
        if not isinstance(includes, dict) or not 1 <= len(includes) <= 256 or model_name in includes:
            raise ValueError("Invalid Poly Haven glTF dependency list")
        for name in includes:
            if not re.fullmatch(r"(?:textures/)?[A-Za-z0-9_-][A-Za-z0-9_. -]{0,199}", name):
                raise ValueError("Unsafe Poly Haven glTF dependency name")
        downloads = self._download_files([(model_name, model), *sorted(includes.items())], cache, budget)

        def read_dependency(name):
            return downloads[name][0].read_bytes() if name in includes else None

        body = pack_gltf(downloads[model_name][0].read_bytes(), read_dependency, texture_subdirectory=True)
        records = [details | {"member": name} for name, (_, details) in downloads.items()]
        provenance = Provenance(name=entry["name"], creator=entry["creator"], source_url=entry["source_url"],
            license_id="CC0-1.0", license_text=cc0_text(), approval="approved", render_allowed=True,
            redistribution_allowed=True, category=entry["category"], tags=entry["tags"], attribution=self.label,
            description=f"Official {resolution} glTF {model_name} embedded as static GLB. "
                        f"Source glTF SHA256 {downloads[model_name][1]['sha256']}.")
        with tempfile.TemporaryDirectory(prefix="atlas-asset-") as temp:
            source = Path(temp) / "asset.glb"
            source.write_bytes(body)
            record = AssetRegistry(library).register(source, entry["id"], provenance)
        return {"catalog": entry, "files": records, "asset": record, "resolution": resolution,
                "source_format": "gltf", "status": "registered-glb"}


AMBIENT_API = "https://ambientcg.com/api/v3/assets"
AMBIENT_MAPS = {
    "Color": "Diffuse", "Roughness": "Rough", "NormalGL": "nor_gl", "Metalness": "Metal",
    "Height": "Height", "Displacement": "Displacement", "AmbientOcclusion": "AO", "Opacity": "Opacity",
    "Emission": "Emission",
}


def _cache_texture(data: bytes, cache: Path) -> str:
    digest = hashlib.sha256(data).hexdigest()
    blob = contained_path(cache, f"blobs/{digest}")
    if blob.is_file() and file_hash(blob) == digest:
        return digest
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=blob.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(blob)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return digest


@dataclass(frozen=True)
class AmbientCG:
    id: str = "ambientcg"
    label: str = "ambientCG CC0 materials"

    def discover(self):
        results = []
        for offset in range(0, 10000, 250):
            url = f"{AMBIENT_API}?type=material&sort=alphabet&limit=250&offset={offset}&include=tags,releaseDate"
            response = json.loads(fetch_bytes(url))
            for item in response["assets"]:
                slug = item["id"]
                if not re.fullmatch(r"[A-Za-z0-9]{1,80}", slug):
                    continue
                name = re.sub(r"(?<=[a-z])(?=[A-Z0-9])", " ", slug)
                results.append({"id": f"ambientcg-{slug.lower()}", "provider": self.id, "name": name,
                    "slug": slug, "category": "material", "style": "photorealistic",
                    "tags": sorted(set(item.get("tags", []))), "creator": "ambientCG / Lennart Demes",
                    "source_url": f"https://ambientcg.com/a/{slug}", "license_id": "CC0-1.0",
                    "revision": item.get("releaseDate", ""), "credit": self.label})
            if offset + 250 >= response["totalResults"]:
                return results
        raise ValueError("ambientCG material catalog exceeds 10,000 assets")

    def acquire(self, entry, cache, library, budget, *, resolution="1k", source_format=None):
        slug = entry["slug"]
        if (not re.fullmatch(r"[A-Za-z0-9]{1,80}", slug) or entry["id"] != f"ambientcg-{slug.lower()}"
                or entry["category"] != "material"):
            raise ValueError("Invalid ambientCG material identity")
        extension = source_format or "jpg"
        if extension not in {"jpg", "png"}:
            raise ValueError("ambientCG material source formats are jpg and png")
        variant = f"{resolution.upper()}-{extension.upper()}"
        response = json.loads(fetch_bytes(f"{AMBIENT_API}?type=material&id={slug}&include=downloads"))
        selected = [item for asset in response["assets"] if asset["id"] == slug for item in asset["downloads"]
                    if item["attributes"] == variant and item["extension"] == "zip"]
        if len(selected) != 1:
            raise ValueError(f"ambientCG does not offer an unambiguous {variant} material archive for {slug}")
        item = selected[0]
        archive_path, transfer = download(item["url"], cache, budget, expected_size=item["size"])
        records = self._extract_material(archive_path, cache, slug, resolution, extension)
        result = {"catalog": entry, "download": transfer, "files": records, "license_text": cc0_text(),
                  "status": "cached-source", "resolution": resolution, "source_format": extension}
        return result | {"fingerprint": media_fingerprint(result)}

    @staticmethod
    def _extract_material(archive_path, cache, slug, resolution, extension):
        pattern = re.compile(rf"{re.escape(slug)}_{resolution}(?:-{extension})?_([A-Za-z]+)\.{extension}",
                             flags=re.IGNORECASE)
        signature = b"\x89PNG\r\n\x1a\n" if extension == "png" else b"\xff\xd8\xff"
        with ZipFile(archive_path) as archive:
            selected = {}
            for name, info in unpack_models(archive).items():
                match = pattern.fullmatch(PurePosixPath(name).name)
                channel = AMBIENT_MAPS.get(match[1]) if match else None
                if channel is None:
                    continue
                if channel in selected:
                    raise ValueError(f"Duplicate ambientCG material channel: {channel}")
                selected[channel] = info
            if not {"Diffuse", "Rough", "nor_gl"}.issubset(selected):
                raise ValueError("ambientCG package is missing color, roughness or OpenGL normal")
            files = []
            for channel, info in sorted(selected.items()):
                data = archive.read(info)
                if not data.startswith(signature):
                    raise ValueError(f"ambientCG texture signature mismatch: {info.filename}")
                files.append({"channel": channel, "member": info.filename, "format": extension,
                              "sha256": _cache_texture(data, cache), "bytes": len(data)})
        return files


SMITHSONIAN_API = "https://3d-api.si.edu/api/v1.0/content/file/search"
SMITHSONIAN_PACKAGE = "ff607e3c-3d88-4422-a246-3976aa4839dc"
SMITHSONIAN_FILE = "chair-(england)-1750-60-150k-4096.glb"
SMITHSONIAN_OBJECT = f"https://3d.si.edu/object/3d/side-chair%3A{SMITHSONIAN_PACKAGE}"


@dataclass(frozen=True)
class Smithsonian:
    id: str = "smithsonian"
    label: str = "Smithsonian Open Access, reviewed CC0 objects"

    def discover(self):
        response = json.loads(fetch_bytes(f"{SMITHSONIAN_API}?model_url={SMITHSONIAN_PACKAGE}&file_type=glb"))
        uri = f"https://3d-api.si.edu/content/document/3d_package:{SMITHSONIAN_PACKAGE}/resources/{SMITHSONIAN_FILE}"
        matching = [row["content"] for row in response["rows"] if row["content"]["uri"] == uri]
        if len(matching) != 1:
            raise ValueError("Smithsonian is missing the reviewed Rococo Side Chair derivative")
        source = matching[0]
        if (source["model_url"] != f"3d_package:{SMITHSONIAN_PACKAGE}" or source["usage"] != "Download3D"
                or source["file_type"].lower() != "glb" or source.get("draco_compressed")
                or source.get("gltf_orientation_compliant") is not True
                or type(source["file_size"]) is not int or source["file_size"] < 1):
            raise ValueError("Smithsonian changed the reviewed Rococo Side Chair derivative")
        # Object-level CC0, date and material were checked against this exact museum record.
        return [{"id": "smithsonian-rococo-side-chair", "provider": self.id, "name": "Rococo Side Chair",
            "category": "environment", "style": "photorealistic", "tags": ["furniture", "chair", "wood", "rococo", "1750s"],
            "creator": "Cooper Hewitt, Smithsonian Design Museum",
            "credit": "Museum purchase from General Acquisitions Endowment Fund",
            "source_url": SMITHSONIAN_OBJECT, "license_id": "CC0-1.0", "accession": "2006-5-1",
            "date": "1750–60", "material": "red walnut, silk damask (modern)", "place": "probably Birmingham, England",
            "revision": f"{SMITHSONIAN_PACKAGE}/{SMITHSONIAN_FILE}",
            "archive_url": uri, "size": source["file_size"], "meters_per_unit": 0.001}]

    def acquire(self, entry, cache, library, budget, *, resolution="1k", source_format=None):
        if resolution != "1k" or source_format not in {None, "glb"}:
            raise ValueError("The reviewed Smithsonian derivative is a fixed GLB")
        if self.discover() != [entry]:
            raise ValueError("Smithsonian catalog record differs from the reviewed derivative; synchronize again")
        path, transfer = download(entry["archive_url"], cache, budget, expected_size=entry["size"])
        body = scale_static_glb(path, entry["meters_per_unit"])
        provenance = Provenance(name=entry["name"], creator=entry["creator"], source_url=entry["source_url"],
            license_id="CC0-1.0", license_text=cc0_text(), approval="approved", render_allowed=True,
            redistribution_allowed=True, category=entry["category"], tags=entry["tags"],
            attribution=f"{entry['creator']}, {entry['credit']}.",
            description=f"Accession {entry['accession']}, {entry['date']}, {entry['place']}. {entry['material']}. "
                        f"Official source GLB SHA256 {transfer['sha256']}. Source units converted to meters.")
        with tempfile.TemporaryDirectory(prefix="atlas-asset-") as temp:
            source = Path(temp) / "asset.glb"
            source.write_bytes(body)
            record = AssetRegistry(library).register(source, entry["id"], provenance)
        return {"catalog": entry, "download": transfer, "asset": record, "source_format": "glb",
                "status": "registered-glb"}


PROVIDERS: dict[str, Provider] = {p.id: p for p in (KayKit(), PolyHaven(), AmbientCG(), Smithsonian())}


def store_catalog(provider: str, root: Path, entries: list[dict], credit: str, *, replace: bool) -> dict:
    if len({entry["id"] for entry in entries}) != len(entries):
        raise ValueError("Provider returned duplicate catalog IDs")
    result = {"provider": provider, "credit": credit, "synced_at": utc_now(), "entries": entries}
    root.mkdir(parents=True, exist_ok=True)
    with _catalog_db(root) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS catalog (
            id TEXT PRIMARY KEY, provider TEXT NOT NULL, category TEXT NOT NULL,
            style TEXT NOT NULL, text TEXT NOT NULL, record TEXT NOT NULL)""")
        db.execute("CREATE INDEX IF NOT EXISTS by_provider_category ON catalog(provider, category, id)")
        if replace:
            db.execute("DELETE FROM catalog WHERE provider = ?", (provider,))
        db.executemany("INSERT OR REPLACE INTO catalog VALUES (?,?,?,?,?,?)", [
            (e["id"], provider, e["category"], e["style"],
             " ".join([e["id"], e["name"], e["category"], e["style"], e.get("description") or "",
                       e.get("category_path") or "", *e["tags"]]).casefold(),
             json.dumps(e | {"catalog_synced_at": result["synced_at"]}, ensure_ascii=False)) for e in entries])
    return result


def synchronize(provider: str, root: Path) -> dict:
    adapter = PROVIDERS[provider]
    return store_catalog(provider, root, adapter.discover(), adapter.label, replace=True)


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


def search_catalog(root: Path, query="", *, category=None, style=None, provider=None, seed=None, offset=0,
                   limit=50) -> list[dict]:
    if offset < 0 or not 1 <= limit <= 1000:
        raise ValueError("Catalog page requires nonnegative offset and limit 1–1000")
    if len(query) > 500:
        raise ValueError("Catalog query exceeds 500 characters")
    if not _catalog_exists(root):
        return []
    where = ["instr(text, ?) > 0" for _ in query.split()]
    params = query.casefold().split()
    for column, value in (("category", category), ("style", style), ("provider", provider)):
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


def catalog_entry(asset_id: str, cache: Path) -> dict:
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
    if entry.get("id") != asset_id or entry.get("provider") != provider:
        raise ValueError("Catalog record identity does not match its index")
    return entry


def asset_variants(asset_id: str, cache: Path) -> list[dict]:
    entry = catalog_entry(asset_id, cache)
    if entry["provider"] != "polyhaven":
        raise ValueError("Resolution variant preflight is supported for Poly Haven assets")
    return PolyHaven.variants(PolyHaven.file_index(entry), entry["category"])


def acquire(asset_id: str, cache: Path, library: Path, budget: int = 64 * MIB, *,
            resolution: str = "1k", source_format: str | None = None, max_texture_size: int = 4096) -> dict:
    entry = catalog_entry(asset_id, cache)
    provider = entry["provider"]
    if resolution not in RESOLUTIONS and (provider != "polyhaven" or resolution != "auto"):
        raise ValueError("Resolution must be 1k, 2k or 4k, or auto for Poly Haven")
    options = {"max_texture_size": max_texture_size} if provider == "polyhaven" else {}
    try:
        result = PROVIDERS[provider].acquire(entry, cache, library, budget, resolution=resolution,
                                             source_format=source_format, **options)
    except (BadZipFile, KeyError, TypeError, UnicodeError) as exc:
        raise ValueError(f"Malformed provider asset or response: {asset_id}: {exc}") from exc
    if "fingerprint" in result:
        version = contained_path(cache, f"media-versions/{asset_id}/{result['fingerprint']}.json")
        if not version.exists():
            atomic_json(version, result)
    if "asset" in result:
        asset = result["asset"]
        version = contained_path(cache, f"model-versions/{asset_id}/{asset['version']}-{asset['sha256']}.json")
        if not version.exists():
            atomic_json(version, result)
    atomic_json(contained_path(cache, f"acquired/{asset_id}.json"), result)
    return result
