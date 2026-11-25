"""Asset discovery, acquisition, and local library subcommands."""
import argparse
from contextlib import nullcontext
import os
from pathlib import Path
import tempfile
from zipfile import BadZipFile

from engine.assets.batch import BatchPlan, apply_batch, scan_directory
from engine.assets.blendkit import ADDON_URL, ADDON_VERSION, import_blendkit
from engine.assets.inspection import inspect_asset
from engine.assets.models import Provenance
from engine.assets.registry import AssetRegistry, file_hash
from engine.assets.thumbnails import create_thumbnail
from engine.assets.providers import PACKS, PROVIDERS, RESOLUTIONS, acquire, asset_variants, search_catalog, store_catalog, synchronize
from engine.assets.acquisition import MIB, cache_blobs, cache_limit, isolate_root_mesh, read_archive_model
from engine.assets.selection import AssetRequirements, select_assets
from engine.assets.sketchfab import sketchfab_auth_status, sketchfab_login
from engine.core.models import EnvironmentCollection
from engine.storage.jobs import atomic_json, contained_path


PROVIDER_NAMES = (*sorted(PROVIDERS), "blendkit")


def add_asset_commands(subparsers):
    group = subparsers.add_parser("assets", help="acquire, register and inspect production assets")
    commands = group.add_subparsers(dest="asset_command", required=True)
    commands.add_parser("providers", help="list supported acquisition providers")
    doctor = commands.add_parser("doctor", help="report local asset-library and provider setup")
    auth = commands.add_parser("auth", help="verify authorized Sketchfab account access")
    auth.add_argument("provider", choices=["sketchfab"])
    auth.add_argument("--login", action="store_true", help="open official OAuth consent for a registered application")
    sync = commands.add_parser("sync", help="synchronize an official provider catalog")
    sync.add_argument("provider", choices=sorted(PROVIDERS))
    sync.add_argument("--query", help="Sketchfab search query")
    sync.add_argument("--category", action="append", default=[], help="Sketchfab category slug, repeatable")
    sync.add_argument("--tag", action="append", default=[], help="Sketchfab tag, repeatable")
    sync.add_argument("--pages", type=int, default=1, help="maximum Sketchfab search result pages")
    catalog = commands.add_parser("catalog", help="search synchronized provider metadata")
    catalog.add_argument("query", nargs="?", default="")
    catalog.add_argument("--category", choices=["character", "environment", "hdri", "material", "prop"])
    catalog.add_argument("--style")
    catalog.add_argument("--provider", choices=PROVIDER_NAMES)
    catalog.add_argument("--seed", type=int)
    catalog.add_argument("--offset", type=int, default=0)
    catalog.add_argument("--limit", type=int, default=50)
    download = commands.add_parser("download", help="acquire one eligible catalog asset")
    download.add_argument("id")
    download.add_argument("--budget-mib", type=int, default=64)
    download.add_argument("--resolution", choices=(*RESOLUTIONS, "auto"), type=str.lower, default="1k")
    download.add_argument("--max-texture-size", type=int, choices=[1024, 2048, 4096], default=4096,
                          help="maximum texture tier when selecting a Poly Haven derivative automatically")
    download.add_argument("--format", dest="source_format", choices=["gltf", "glb", "jpg", "png", "hdr"], type=str.lower,
                          help="source derivative format (provider-specific default if omitted)")
    download.add_argument("--library", type=Path, default=Path("assets/library"))
    download.add_argument("--sketchfab-login", action="store_true", help="authorize this Sketchfab download using browser OAuth")
    variants = commands.add_parser("variants", help="estimate official Poly Haven derivative bytes before download")
    variants.add_argument("id")
    pack = commands.add_parser("download-pack", help="acquire the reviewed starter subset of one KayKit pack")
    pack.add_argument("id", choices=sorted(PACKS))
    pack.add_argument("--budget-mib", type=int, default=64)
    pack.add_argument("--library", type=Path, default=Path("assets/library"))
    storage = commands.add_parser("storage", help="report local acquisition cache usage")
    storage.add_argument("--library", type=Path, default=Path("assets/library"))
    select = commands.add_parser("select", help="rank candidates using structured requirements and verified local evidence")
    select.add_argument("requirements", type=Path)
    select.add_argument("--seed", type=int, default=0)
    select.add_argument("--limit", type=int, default=20)
    collections = commands.add_parser("collections", help="validate and list reusable environment collections")
    collections.add_argument("--root", type=Path, default=Path("examples/collections"))
    licenses = commands.add_parser("licenses", help="list declared provenance for local production assets")
    licenses.add_argument("--library", type=Path, default=Path("assets/library"))
    for command in (sync, catalog, download, pack, storage, variants, select, doctor):
        command.add_argument("--cache", type=Path, default=Path("assets/acquisition"))
    register = commands.add_parser("register", help="copy a local GLB with declared license provenance")
    register.add_argument("source", type=Path)
    register.add_argument("--id", required=True)
    register.add_argument("--provenance", type=Path, required=True)
    register.add_argument("--profile", choices=["static", "pbr", "rigged"], default="static")
    manual = commands.add_parser("import-archive", help="register an explicit GLB/glTF member from an approved ZIP")
    manual.add_argument("source", type=Path)
    manual.add_argument("--member", required=True)
    manual.add_argument("--id", required=True)
    manual.add_argument("--provenance", type=Path, required=True)
    manual.add_argument("--profile", choices=["static", "pbr", "rigged"], default="static")
    native = commands.add_parser("import-blendkit", help="convert a reviewed free CC0 Blendkit native asset locally")
    native.add_argument("source", type=Path)
    native.add_argument("--id", required=True)
    native.add_argument("--provider-asset-id", required=True)
    native.add_argument("--plan", choices=["free"], required=True)
    native.add_argument("--provenance", type=Path, required=True)
    selected = native.add_mutually_exclusive_group(required=True)
    selected.add_argument("--object", action="append", default=[], help="selected object name, repeatable")
    selected.add_argument("--collection", action="append", default=[], help="selected collection name, repeatable")
    native.add_argument("--blender", type=Path)
    native.add_argument("--cache", type=Path, default=Path("assets/acquisition"))
    search = commands.add_parser("search", help="search latest versions by literal metadata")
    search.add_argument("--query", default="")
    search.add_argument("--tag")
    search.add_argument("--category")
    search.add_argument("--license", dest="license_id")
    show = commands.add_parser("show", help="show one immutable version and its inspection status")
    inspect = commands.add_parser("inspect", help="inspect an approved GLB using Blender")
    thumbnail = commands.add_parser("thumbnail", help="render and verify a studio PNG for an inspected asset")
    normalize = commands.add_parser("normalize", help="report deterministic unit/base transform for an inspected GLB")
    derive = commands.add_parser("derive-module", help="register and inspect a named static root mesh from an approved GLB")
    derive.add_argument("--node", required=True)
    derive.add_argument("--output-id", required=True)
    derive.add_argument("--blender", type=Path)
    for command in (show, inspect, thumbnail, normalize, derive):
        command.add_argument("id")
        command.add_argument("--version", type=int, required=True)
    inspect.add_argument("--blender", type=Path)
    thumbnail.add_argument("--blender", type=Path)
    thumbnail.add_argument("--size", type=int, choices=[128, 256, 512], default=256)
    scan = commands.add_parser("scan", help="write an unselected, hash-bound directory review plan")
    scan.add_argument("root", type=Path)
    scan.add_argument("--plan", type=Path)
    scan.add_argument("--no-recursive", action="store_true")
    batch = commands.add_parser("batch", help="apply a reviewed plan with isolated per-file outcomes")
    batch.add_argument("plan", type=Path)
    batch.add_argument("--root", type=Path, required=True)
    batch.add_argument("--inspect", action="store_true")
    batch.add_argument("--thumbnails", action="store_true")
    batch.add_argument("--size", type=int, choices=[128, 256, 512], default=256)
    batch.add_argument("--blender", type=Path)
    for command in (register, manual, native, search, show, inspect, thumbnail, normalize, derive, batch, select, doctor):
        command.add_argument("--library", type=Path, default=Path("assets/library"))


def run_asset_command(args: argparse.Namespace):
    if args.asset_command == "providers":
        return [{"id": provider.id, "name": provider.label} for provider in PROVIDERS.values()] + [
            {"id": "blendkit", "name": "Blendkit official add-on and reviewed native import", "mode": "user-mediated"}]
    if args.asset_command == "doctor":
        return {"catalog_initialized": contained_path(args.cache, "catalog.sqlite3").is_file(),
                "library_initialized": contained_path(args.library, "assets.sqlite3").is_file(),
                "sketchfab_access_token_configured": bool(os.environ.get("ATLAS_SKETCHFAB_ACCESS_TOKEN")),
                "sketchfab_oauth_client_configured": bool(os.environ.get("ATLAS_SKETCHFAB_CLIENT_ID")),
                "blendkit": {"workflow": "user-mediated", "tested_addon": ADDON_VERSION, "release": ADDON_URL}}
    if args.asset_command == "auth":
        with sketchfab_login() if args.login else nullcontext():
            return sketchfab_auth_status()
    if args.asset_command == "sync":
        if args.provider == "sketchfab":
            adapter = PROVIDERS["sketchfab"]
            entries = adapter.discover(args.query, categories=args.category, tags=args.tag, pages=args.pages)
            result = store_catalog(args.provider, args.cache, entries, adapter.label, replace=False)
        else:
            if args.query or args.category or args.tag or args.pages != 1:
                raise ValueError("Remote query filters are supported for Sketchfab sync")
            result = synchronize(args.provider, args.cache)
        return {"provider": result["provider"], "credit": result["credit"], "cataloged": len(result["entries"])}
    if args.asset_command == "catalog":
        return search_catalog(args.cache, args.query, category=args.category, style=args.style, seed=args.seed,
                              provider=args.provider, offset=args.offset, limit=args.limit)
    if args.asset_command == "variants":
        return asset_variants(args.id, args.cache)
    if args.asset_command == "download":
        if args.id.startswith("blendkit-"):
            raise ValueError("Download through the official Blendkit add-on and run assets import-blendkit")
        if args.sketchfab_login and not args.id.startswith("sketchfab-"):
            raise ValueError("Browser OAuth login applies only to a Sketchfab asset")
        with sketchfab_login() if args.sketchfab_login else nullcontext():
            return acquire(args.id, args.cache, args.library, args.budget_mib * MIB,
                           resolution=args.resolution, source_format=args.source_format,
                           max_texture_size=args.max_texture_size)
    if args.asset_command == "download-pack":
        selected = [entry for entry in PROVIDERS["kaykit"].discover() if entry["pack"] == args.id]
        records = [acquire(entry["id"], args.cache, args.library, args.budget_mib * MIB) for entry in selected]
        return {"pack": args.id, "count": len(records), "assets": records}
    if args.asset_command == "storage":
        blobs = cache_blobs(args.cache)
        derivatives = [path for path in contained_path(args.library, "blobs").glob("*.glb") if path.is_file()]
        native_sources = [p for p in contained_path(args.library, "blendkit-private/sources").glob("*.blend") if p.is_file()]
        return {"blobs": len(blobs), "bytes": sum(path.stat().st_size for path in blobs), "cache_limit_bytes": cache_limit(),
                "acquired": len(list(contained_path(args.cache, "acquired").glob("*.json"))),
                "private_native_bytes": sum(p.stat().st_size for p in native_sources),
                "registered_blob_count": len(derivatives), "registered_bytes": sum(p.stat().st_size for p in derivatives)}
    if args.asset_command == "select":
        if args.requirements.stat().st_size > 64 * 1024:
            raise ValueError("Selection requirements exceed 64 KiB")
        specification = AssetRequirements.model_validate_json(args.requirements.read_text(encoding="utf-8-sig"))
        return select_assets(specification, args.cache, args.library, seed=args.seed, limit=args.limit)
    if args.asset_command == "collections":
        if not args.root.is_dir():
            raise ValueError("Environment collection directory does not exist")
        results = []
        for path in sorted(args.root.glob("*.json")):
            if path.stat().st_size > MIB:
                raise ValueError(f"Collection exceeds 1 MiB: {path.name}")
            collection = EnvironmentCollection.model_validate_json(path.read_text(encoding="utf-8-sig"))
            results.append({"id": collection.id, "entity_count": len(collection.entities), "file": str(path.resolve())})
        return results
    if args.asset_command == "scan":
        if args.plan and args.plan.exists():
            raise FileExistsError(f"Review plan already exists: {args.plan}; choose a new path to preserve selections")
        plan = scan_directory(args.root, recursive=not args.no_recursive)
        result = plan.model_dump(mode="json")
        if args.plan:
            atomic_json(args.plan.resolve(), result)
        return result
    if args.asset_command == "batch":
        if args.plan.stat().st_size > 20 * 1024 * 1024:
            raise ValueError("Batch plan exceeds 20 MiB")
        plan = BatchPlan.model_validate_json(args.plan.read_text(encoding="utf-8-sig"))
        return apply_batch(plan, args.root, args.library, inspect=args.inspect, thumbnails=args.thumbnails,
                           size=args.size, blender=args.blender)
    database = contained_path(args.library, "assets.sqlite3")
    if args.asset_command not in {"register", "import-archive", "import-blendkit"} and not database.is_file():
        if args.asset_command in {"search", "licenses"}:
            return []
        raise ValueError(f"Asset library does not exist: {args.library}")
    if args.asset_command in {"register", "import-archive", "import-blendkit"}:
        if args.provenance.stat().st_size > 500000:
            raise ValueError("Provenance JSON exceeds 500 KB")
        provenance = Provenance.model_validate_json(args.provenance.read_text(encoding="utf-8-sig"))
        if args.asset_command == "import-blendkit":
            if not args.id.startswith("blendkit-"):
                raise ValueError("Blendkit IDs must begin with blendkit-")
            receipt = import_blendkit(args.source, args.id, provenance, AssetRegistry(args.library),
                                      provider_asset_id=args.provider_asset_id, plan=args.plan,
                                      objects=tuple(args.object), collections=tuple(args.collection), blender=args.blender)
            store_catalog("blendkit", args.cache, [{"id": args.id, "provider": "blendkit", "name": provenance.name,
                "provider_asset_id": receipt["provider_asset_id"], "category": provenance.category,
                "style": "photorealistic" if "realistic" in provenance.tags else "unclassified",
                "tags": provenance.tags, "description": provenance.description, "creator": provenance.creator,
                "source_url": provenance.source_url, "license_id": provenance.license_id,
                "license_url": receipt["license_url"], "redistribution_allowed": False,
                "source_format": "blend"}], "Blendkit official add-on", replace=False)
            return receipt
        if args.asset_command == "import-archive":
            provenance.require_render_rights()
            try:
                body = read_archive_model(args.source, args.member)
            except (BadZipFile, KeyError, TypeError, UnicodeError) as exc:
                raise ValueError(f"Malformed archive model: {exc}") from exc
            provenance.description += f" Source archive SHA256 {file_hash(args.source)}. Member: {args.member}."
            with tempfile.TemporaryDirectory(prefix="atlas-archive-") as temp:
                source = Path(temp) / "model.glb"
                source.write_bytes(body)
                return AssetRegistry(args.library).register(source, args.id, provenance, profile=args.profile)
        return AssetRegistry(args.library).register(args.source, args.id, provenance, profile=args.profile)
    registry = AssetRegistry(args.library)
    if args.asset_command == "licenses":
        return [{"id": e["id"], "version": e["version"], "provenance": e["provenance"]} for e in registry.search()]
    if args.asset_command == "search":
        return registry.search(query=args.query, tag=args.tag, category=args.category, license_id=args.license_id)
    if args.asset_command == "show":
        return registry.get(args.id, args.version)
    if args.asset_command == "thumbnail":
        return create_thumbnail(registry, args.id, args.version, size=args.size, blender=args.blender)
    if args.asset_command == "derive-module":
        if args.id == args.output_id or not 1 <= len(args.node) <= 160:
            raise ValueError("Choose a distinct output ID and a root mesh name up to 160 characters")
        entry = registry.resolve(args.id, args.version)
        profile = entry["container"].get("profile", "static")
        body = isolate_root_mesh(entry["path"], args.node, profile=profile)
        provenance = Provenance.model_validate(entry["provenance"])
        provenance.name = args.output_id
        lineage = f"Derived root mesh {args.node!r} from {args.id}@{args.version} ({entry['sha256']}). Removed the source display offset."
        provenance.description = lineage
        if provenance.license_id == "CC-BY-4.0":
            provenance.attribution += f" Changes: {lineage}"
        with tempfile.TemporaryDirectory(prefix="atlas-module-") as temp:
            source = Path(temp) / "module.glb"
            source.write_bytes(body)
            record = registry.register(source, args.output_id, provenance, profile=profile)
        if record["inspection"]["status"] != "ready":
            inspect_asset(registry, args.output_id, record["version"], blender=args.blender)
        return registry.get(args.output_id, record["version"])
    if args.asset_command == "normalize":
        entry = registry.resolve(args.id, args.version)
        report = entry["inspection"]["report"]
        lo, hi = report["bounds"]["min"], report["bounds"]["max"]
        scale = 1 / max(report["dimensions"])
        return {"id": args.id, "version": args.version, "source_sha256": entry["sha256"],
            "profile": "atlas-parent-transform-1", "unit_scale": scale,
            "base_origin": [(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]]}
    return inspect_asset(registry, args.id, args.version, blender=args.blender)
