"""Queries over inspected source rigs and their compatible embedded clips."""
from pathlib import Path

from engine.assets.registry import AssetRegistry
from engine.storage.jobs import contained_path
from engine.characters.mpfb import HumanSpec, generate, install_runtime


def add_character_commands(subparsers):
    for name in ("characters", "animations"):
        area = subparsers.add_parser(name, help=f"query approved inspected {name}")
        commands = area.add_subparsers(dest="rig_command", required=True)
        listing = commands.add_parser("list")
        listing.add_argument("--character")
        inspect = commands.add_parser("inspect")
        inspect.add_argument("character")
        for command in (listing, inspect):
            command.add_argument("--version", type=int, default=1)
            command.add_argument("--library", type=Path, default=Path("assets/library"))
        if name == "animations":
            inspect.add_argument("clip")
            check = commands.add_parser("compatibility")
            check.add_argument("character")
            check.add_argument("clip")
            check.add_argument("--version", type=int, default=1)
            check.add_argument("--library", type=Path, default=Path("assets/library"))
        else:
            runtime = commands.add_parser("install-mpfb", help="install the pinned MPFB runtime and CC0 source packs")
            runtime.add_argument("--runtime", type=Path, default=Path("outputs/v051-mpfb"))
            runtime.add_argument("--blender", type=Path)
            generation = commands.add_parser("generate", help="generate and inspect a reusable clothed MPFB human")
            generation.add_argument("spec", type=Path)
            generation.add_argument("--runtime", type=Path, default=Path("outputs/v051-mpfb"))
            generation.add_argument("--library", type=Path, default=Path("assets/library"))
            generation.add_argument("--blender", type=Path)
            validate = commands.add_parser("validate")
            validate.add_argument("character")
            validate.add_argument("--version", type=int, default=1)
            validate.add_argument("--library", type=Path, default=Path("assets/library"))


def run_character_command(args):
    if args.rig_command == "install-mpfb":
        return install_runtime(args.runtime, blender=args.blender)
    if args.rig_command == "generate":
        if args.spec.stat().st_size > 256 * 1024:
            raise ValueError("Human specification exceeds 256 KiB")
        spec = HumanSpec.model_validate_json(args.spec.read_text(encoding="utf-8-sig"))
        return generate(spec, args.runtime, args.library, blender=args.blender)
    if not contained_path(args.library, "assets.sqlite3").is_file():
        raise ValueError("Asset library does not exist. Acquire and inspect a rig first.")
    registry = AssetRegistry(args.library)
    if args.rig_command == "list" and not args.character:
        candidates = [e for e in registry.search() if e["container"].get("profile") in {"rigged", "human"}
                      and e["inspection"]["status"] == "ready"]
    else:
        candidates = [registry.get(args.character, args.version)]
    results = []
    for candidate in candidates:
        if candidate["container"].get("profile") not in {"rigged", "human"}:
            raise ValueError("Selected asset does not use the rigged GLB profile")
        entry = registry.resolve(candidate["id"], candidate["version"])
        report = entry["inspection"]["report"]
        identity = {"character": entry["id"], "version": entry["version"], "skeleton_sha256": report["skeleton_sha256"]}
        if args.command == "characters":
            results.append(identity | (report if args.rig_command != "list" else {
                "clips": len(report["clips"]), "humanoid": bool(report["humanoid_mapping"]),
                "facial_controls": bool(report["facial_shape_keys"] or report["jaw_bones"])}))
        else:
            wanted = getattr(args, "clip", None)
            for clip in report["clips"]:
                if wanted is None or wanted == clip["name"]:
                    results.append(identity | clip | {"compatibility": "embedded on this exact source version"})
    if args.rig_command == "compatibility":
        return {"compatible": bool(results), "clips": results,
                "reason": "Clip is embedded on this exact rig" if results else "Clip is absent from the pinned source rig"}
    if args.rig_command == "inspect" and args.command == "animations" and not results:
        raise ValueError("Clip is absent from the pinned source rig")
    return results if args.rig_command == "list" else results[0]
