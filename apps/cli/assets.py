"""Asset library subcommands. No network or implicit license approvals."""
import argparse
from pathlib import Path

from engine.assets.batch import BatchPlan, apply_batch, scan_directory
from engine.assets.inspection import inspect_asset
from engine.assets.models import Provenance
from engine.assets.registry import AssetRegistry
from engine.assets.thumbnails import create_thumbnail
from engine.storage.jobs import atomic_json, contained_path


def add_asset_commands(subparsers):
    group = subparsers.add_parser("assets", help="register, inspect and search approved local GLBs")
    commands = group.add_subparsers(dest="asset_command", required=True)
    register = commands.add_parser("register", help="copy a local GLB with declared license provenance")
    register.add_argument("source", type=Path)
    register.add_argument("--id", required=True)
    register.add_argument("--provenance", type=Path, required=True)
    search = commands.add_parser("search", help="search latest versions by literal metadata")
    search.add_argument("--query", default="")
    search.add_argument("--tag")
    search.add_argument("--category")
    search.add_argument("--license", dest="license_id")
    show = commands.add_parser("show", help="show one immutable version and its inspection status")
    inspect = commands.add_parser("inspect", help="inspect an approved GLB using Blender")
    thumbnail = commands.add_parser("thumbnail", help="render and verify a studio PNG for an inspected asset")
    for command in (show, inspect, thumbnail):
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
    for command in (register, search, show, inspect, thumbnail, batch):
        command.add_argument("--library", type=Path, default=Path("assets/library"))


def run_asset_command(args: argparse.Namespace):
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
    if args.asset_command != "register" and not database.is_file():
        if args.asset_command == "search":
            return []
        raise ValueError(f"Asset library does not exist: {args.library}")
    if args.asset_command == "register":
        if args.provenance.stat().st_size > 500000:
            raise ValueError("Provenance JSON exceeds 500 KB")
        provenance = Provenance.model_validate_json(args.provenance.read_text(encoding="utf-8-sig"))
        return AssetRegistry(args.library).register(args.source, args.id, provenance)
    registry = AssetRegistry(args.library)
    if args.asset_command == "search":
        return registry.search(query=args.query, tag=args.tag, category=args.category, license_id=args.license_id)
    if args.asset_command == "show":
        return registry.get(args.id, args.version)
    if args.asset_command == "thumbnail":
        return create_thumbnail(registry, args.id, args.version, size=args.size, blender=args.blender)
    return inspect_asset(registry, args.id, args.version, blender=args.blender)
