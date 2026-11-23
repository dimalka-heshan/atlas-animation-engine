"""Asset library subcommands. No network or implicit license approvals."""
import argparse
from pathlib import Path

from engine.assets.inspection import inspect_asset
from engine.assets.models import Provenance
from engine.assets.registry import AssetRegistry
from engine.storage.jobs import contained_path


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
    for command in (show, inspect):
        command.add_argument("id")
        command.add_argument("--version", type=int, required=True)
    inspect.add_argument("--blender", type=Path)
    for command in (register, search, show, inspect):
        command.add_argument("--library", type=Path, default=Path("assets/library"))


def run_asset_command(args: argparse.Namespace):
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
    return inspect_asset(registry, args.id, args.version, blender=args.blender)
