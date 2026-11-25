"""Queries over inspected source rigs and their compatible embedded clips."""
from pathlib import Path

from engine.assets.registry import AssetRegistry
from engine.storage.jobs import contained_path
from engine.characters.mpfb import HumanSpec, generate, install_runtime
from engine.characters.motion import load_motion, motions, retarget, summarize


def add_character_commands(subparsers):
    motion = subparsers.add_parser("motions", help="query versioned retargeted motions")
    motion_commands = motion.add_subparsers(dest="rig_command", required=True)
    motion_list = motion_commands.add_parser("list")
    motion_list.add_argument("--category", choices=["idle", "walk", "run", "sit", "gesture"])
    motion_list.add_argument("--query", default="")
    motion_inspect = motion_commands.add_parser("inspect")
    motion_inspect.add_argument("id")
    motion_inspect.add_argument("sha256")
    for command in (motion_list, motion_inspect):
        command.add_argument("--motion-cache", type=Path, default=Path("assets/motions"))
    motion_commands.add_parser("providers")
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
            transfer = commands.add_parser("retarget", help="bake an inspected KayKit clip for an MPFB actor")
            transfer.add_argument("source")
            transfer.add_argument("clip")
            transfer.add_argument("target")
            transfer.add_argument("--id", required=True)
            transfer.add_argument("--source-version", type=int, default=1)
            transfer.add_argument("--target-version", type=int, default=1)
            transfer.add_argument("--source-library", type=Path, default=Path("assets/library"))
            transfer.add_argument("--library", type=Path, default=Path("assets/library"))
            transfer.add_argument("--motion-cache", type=Path, default=Path("assets/motions"))
            transfer.add_argument("--category", choices=["idle", "walk", "run", "sit", "gesture"], default="walk")
            transfer.add_argument("--no-ground", action="store_true")
            transfer.add_argument("--blender", type=Path)
            inspect.add_argument("clip")
            check = commands.add_parser("compatibility")
            check.add_argument("character")
            check.add_argument("clip")
            check.add_argument("--version", type=int, default=1)
            check.add_argument("--library", type=Path, default=Path("assets/library"))
        else:
            rigs = commands.add_parser("rigs", help="show validated humanoid families and exact rest-skeleton pins")
            rigs.add_argument("--library", type=Path, default=Path("assets/library"))
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
    if args.command == "motions":
        if args.rig_command == "providers":
            return [{"id": "kaykit", "license": "CC0-1.0", "format": "inspected-rigged-glb",
                     "target": "mpfb-game-engine"}]
        if args.rig_command == "list":
            return [row for row in motions(args.motion_cache) if (not args.category or row["category"] == args.category)
                    and args.query.casefold() in (row["motion"]["id"] + " " + row["source"]["clip"]).casefold()]
        pin = {"id": args.id, "sha256": args.sha256}
        record, _ = load_motion(args.motion_cache, pin)
        return summarize(pin, record)
    if args.rig_command == "retarget":
        return retarget(args.source, args.clip, args.target, args.id, args.source_library, args.library,
                        args.motion_cache, source_version=args.source_version, target_version=args.target_version,
                        category=args.category, ground=not args.no_ground, blender=args.blender)
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
    if args.rig_command == "rigs" or (args.rig_command == "list" and not args.character):
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
        if args.rig_command == "rigs":
            mapping = report["humanoid_mapping"]
            family = {"pelvis": "mpfb-game-engine", "hips": "kaykit"}.get(mapping.get("pelvis"), "unclassified")
            results.append(identity | {"family": family, "roles": mapping, "bone_count": len(report["skeleton"]),
                "bounds_m": report["dimensions"], "face_keys": report["facial_shape_keys"],
                "coordinate_system": report["coordinate_system"], "clip_count": len(report["clips"])})
            continue
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
    return results if args.rig_command in {"list", "rigs"} else results[0]
