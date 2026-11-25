"""Asset discovery, acquisition, and local library subcommands."""
import argparse
from pathlib import Path
import tempfile
from zipfile import BadZipFile

from engine.assets.batch import BatchPlan, apply_batch, scan_directory
from engine.assets.inspection import inspect_asset
from engine.assets.models import Provenance
from engine.assets.registry import AssetRegistry, file_hash
from engine.assets.thumbnails import create_thumbnail
from engine.assets.providers import PACKS, PROVIDERS, RESOLUTIONS, acquire, asset_variants, search_catalog, synchronize
from engine.assets.acquisition import MIB, read_archive_model
from engine.storage.jobs import atomic_json, contained_path


def add_asset_commands(subparsers):
    group = subparsers.add_parser("assets", help="acquire, register and inspect production assets")
    commands = group.add_subparsers(dest="asset_command", required=True)
    commands.add_parser("providers", help="list supported acquisition providers")
    sync = commands.add_parser("sync", help="synchronize an official provider catalog")
    sync.add_argument("provider", choices=sorted(PROVIDERS))
    catalog = commands.add_parser("catalog", help="search synchronized provider metadata")
    catalog.add_argument("query", nargs="?", default="")
    catalog.add_argument("--category", choices=["character", "environment", "hdri", "material"])
    catalog.add_argument("--style")
    catalog.add_argument("--provider", choices=sorted(PROVIDERS))
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
    variants = commands.add_parser("variants", help="estimate official Poly Haven derivative bytes before download")
    variants.add_argument("id")
    pack = commands.add_parser("download-pack", help="acquire the reviewed starter subset of one KayKit pack")
    pack.add_argument("id", choices=sorted(PACKS))
    pack.add_argument("--budget-mib", type=int, default=64)
    pack.add_argument("--library", type=Path, default=Path("assets/library"))
    storage = commands.add_parser("storage", help="report local acquisition cache usage")
    licenses = commands.add_parser("licenses", help="list declared provenance for local production assets")
    licenses.add_argument("--library", type=Path, default=Path("assets/library"))
    for command in (sync, catalog, download, pack, storage, variants):
        command.add_argument("--cache", type=Path, default=Path("assets/acquisition"))
    register = commands.add_parser("register", help="copy a local GLB with declared license provenance")
    register.add_argument("source", type=Path)
    register.add_argument("--id", required=True)
    register.add_argument("--provenance", type=Path, required=True)
    register.add_argument("--profile", choices=["static", "rigged"], default="static")
    manual = commands.add_parser("import-archive", help="register an explicit GLB/glTF member from an approved ZIP")
    manual.add_argument("source", type=Path)
    manual.add_argument("--member", required=True)
    manual.add_argument("--id", required=True)
    manual.add_argument("--provenance", type=Path, required=True)
    manual.add_argument("--profile", choices=["static", "rigged"], default="static")
    search = commands.add_parser("search", help="search latest versions by literal metadata")
    search.add_argument("--query", default="")
    search.add_argument("--tag")
    search.add_argument("--category")
    search.add_argument("--license", dest="license_id")
    show = commands.add_parser("show", help="show one immutable version and its inspection status")
    inspect = commands.add_parser("inspect", help="inspect an approved GLB using Blender")
    thumbnail = commands.add_parser("thumbnail", help="render and verify a studio PNG for an inspected asset")
    normalize = commands.add_parser("normalize", help="report deterministic unit/base transform for an inspected GLB")
    for command in (show, inspect, thumbnail, normalize):
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
    for command in (register, manual, search, show, inspect, thumbnail, normalize, batch):
        command.add_argument("--library", type=Path, default=Path("assets/library"))


def run_asset_command(args: argparse.Namespace):
    if args.asset_command == "providers":
        return [{"id": provider.id, "name": provider.label} for provider in PROVIDERS.values()]
    if args.asset_command == "sync":
        result = synchronize(args.provider, args.cache)
        return {"provider": result["provider"], "credit": result["credit"], "cataloged": len(result["entries"])}
    if args.asset_command == "catalog":
        return search_catalog(args.cache, args.query, category=args.category, style=args.style, seed=args.seed,
                              provider=args.provider, offset=args.offset, limit=args.limit)
    if args.asset_command == "variants":
        return asset_variants(args.id, args.cache)
    if args.asset_command == "download":
        return acquire(args.id, args.cache, args.library, args.budget_mib * MIB,
                       resolution=args.resolution, source_format=args.source_format, max_texture_size=args.max_texture_size)
    if args.asset_command == "download-pack":
        selected = [entry for entry in PROVIDERS["kaykit"].discover() if entry["pack"] == args.id]
        records = [acquire(entry["id"], args.cache, args.library, args.budget_mib * MIB) for entry in selected]
        return {"pack": args.id, "count": len(records), "assets": records}
    if args.asset_command == "storage":
        blobs = [path for path in contained_path(args.cache, "blobs").glob("*") if path.is_file()]
        return {"blobs": len(blobs), "bytes": sum(path.stat().st_size for path in blobs),
                "acquired": len(list(contained_path(args.cache, "acquired").glob("*.json")))}
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
    if args.asset_command not in {"register", "import-archive"} and not database.is_file():
        if args.asset_command in {"search", "licenses"}:
            return []
        raise ValueError(f"Asset library does not exist: {args.library}")
    if args.asset_command in {"register", "import-archive"}:
        if args.provenance.stat().st_size > 500000:
            raise ValueError("Provenance JSON exceeds 500 KB")
        provenance = Provenance.model_validate_json(args.provenance.read_text(encoding="utf-8-sig"))
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
    if args.asset_command == "normalize":
        entry = registry.resolve(args.id, args.version)
        report = entry["inspection"]["report"]
        lo, hi = report["bounds"]["min"], report["bounds"]["max"]
        scale = 1 / max(report["dimensions"])
        return {"id": args.id, "version": args.version, "source_sha256": entry["sha256"],
            "profile": "atlas-parent-transform-1", "unit_scale": scale,
            "base_origin": [(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]]}
    return inspect_asset(registry, args.id, args.version, blender=args.blender)
