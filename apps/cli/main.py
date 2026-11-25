"""Small working production CLI. Standard output is machine-readable JSON."""
import argparse
import json
import logging
import sqlite3
import subprocess
import sys
from pathlib import Path

from apps.cli.assets import add_asset_commands, run_asset_command
from apps.cli.audio import add_audio_commands, run_audio_command
from apps.cli.voice import add_voice_commands, run_voice_command
from apps.cli.lipsync import add_lipsync_commands, run_lipsync_command
from apps.cli.characters import add_character_commands, run_character_command
from engine import __version__
from engine.core.models import EnvironmentCollection, Project
from engine.core.quality import PRESETS
from engine.production import (CreativePlan, HandoffProject, ProductionError, ProductionWorkspace, capabilities,
                               compile_actions, handoff_preview, preflight, preview, validate_creative_plan)
from engine.rendering.pipeline import render_project
from engine.rendering.runtime import doctor, find_tool
from engine.rendering.video import verify_video
from engine.storage.jobs import list_jobs


class JsonFormatter(logging.Formatter):
    def format(self, record):
        data = {"level": record.levelname, "event": record.getMessage()}
        for key in ("job_id", "directory", "error", "asset_id", "version"):
            if hasattr(record, key):
                data[key] = getattr(record, key)
        return json.dumps(data)


def load_project(path: Path, model: type[Project] = Project) -> Project:
    if path.stat().st_size > 10_000_000:
        raise ValueError("Project JSON exceeds the 10 MB input limit")
    return model.model_validate_json(path.read_text(encoding="utf-8-sig"))


def workspace_for(args) -> ProductionWorkspace:
    return ProductionWorkspace(**{name: getattr(args, name) for name in
        ("output", "asset_library", "asset_cache", "audio_library", "motion_cache") if hasattr(args, name)})


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="atlas", description="ATLAS local 3D animation production")
    root.add_argument("--version", action="version", version=__version__)
    sub = root.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="inspect runtime and installed executables")
    sub.add_parser("schema", help="print the project JSON Schema")
    sub.add_parser("capabilities", help="list versioned production capabilities and contracts")
    director = sub.add_parser("director", help="inspect or validate a creative intent plan")
    director_commands = director.add_subparsers(dest="director_command", required=True)
    director_commands.add_parser("schema")
    director_commands.add_parser("validate").add_argument("plan", type=Path)
    quality = sub.add_parser("quality", help="inspect available Blender production profiles")
    quality.add_subparsers(dest="quality_command", required=True).add_parser("profiles")
    add_asset_commands(sub)
    add_audio_commands(sub)
    add_voice_commands(sub)
    add_lipsync_commands(sub)
    add_character_commands(sub)
    validate = sub.add_parser("validate", help="validate a project and expand procedural placement")
    validate.add_argument("project", type=Path)
    validate.add_argument("--asset-library", type=Path, default=Path("assets/library"))
    validate.add_argument("--asset-cache", type=Path, default=Path("assets/acquisition"))
    validate.add_argument("--environment-collection", type=Path)
    validate.add_argument("--audio-library", type=Path, default=Path("assets/audio"))
    navigation = sub.add_parser("navigation", help="validate and plan bounded actor routes")
    plan = navigation.add_subparsers(dest="plan_command", required=True).add_parser("plan")
    actions = sub.add_parser("actions", help="compile actor commands into transform and motion tracks")
    compile_actions = actions.add_subparsers(dest="plan_command", required=True).add_parser("compile")
    for command in (plan, compile_actions):
        command.add_argument("project", type=Path)
        command.add_argument("--asset-library", type=Path, default=Path("assets/library"))
    render = sub.add_parser("render", help="render and verify a new production job")
    production = sub.add_parser("production", help="run bounded production services")
    production_commands = production.add_subparsers(dest="production_command", required=True)
    preview_parser = production_commands.add_parser("preview")
    handoff_parser = production_commands.add_parser("handoff")
    render.add_argument("--engine", choices=["cycles", "eevee"])
    for command in (render, preview_parser, handoff_parser):
        command.add_argument("project", type=Path)
        command.add_argument("--output", type=Path, default=Path("outputs"))
        command.add_argument("--blender", type=Path)
        command.add_argument("--asset-library", type=Path, default=Path("assets/library"))
        command.add_argument("--asset-cache", type=Path, default=Path("assets/acquisition"))
        command.add_argument("--environment-collection", type=Path)
        command.add_argument("--audio-library", type=Path, default=Path("assets/audio"))
    for area in (validate, render, preview_parser, handoff_parser, plan, compile_actions):
        area.add_argument("--motion-cache", type=Path, default=Path("assets/motions"))
    verify = sub.add_parser("verify", help="verify an existing video against project settings")
    verify.add_argument("video", type=Path)
    verify.add_argument("--project", type=Path, required=True)
    jobs = sub.add_parser("jobs", help="list persistent production history")
    jobs.add_argument("--output", type=Path, default=Path("outputs"))
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("atlas")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    try:
        if args.command == "doctor":
            result = doctor()
            print(json.dumps(result, indent=2))
            return 2 if any("error" in tool for tool in result["tools"].values()) else 0
        if args.command == "schema":
            result = Project.model_json_schema()
        elif args.command == "capabilities":
            result = capabilities().model_dump(mode="json")
        elif args.command == "director":
            if args.director_command == "schema":
                result = CreativePlan.model_json_schema()
            else:
                if args.plan.stat().st_size > 2 * 1024 * 1024:
                    raise ProductionError("plan_size", "Creative plan exceeds the 2 MiB input limit.")
                plan = CreativePlan.model_validate_json(args.plan.read_text(encoding="utf-8-sig"))
                result = validate_creative_plan(plan).model_dump(mode="json")
        elif args.command == "quality":
            result = PRESETS
        elif args.command == "jobs":
            result = list_jobs(args.output.resolve())
        elif args.command == "assets":
            result = run_asset_command(args)
        elif args.command == "audio":
            result = run_audio_command(args)
        elif args.command == "voice":
            result = run_voice_command(args)
        elif args.command == "lipsync":
            result = run_lipsync_command(args)
        elif args.command in {"characters", "animations", "motions"}:
            result = run_character_command(args)
        else:
            is_handoff = args.command == "production" and args.production_command == "handoff"
            project = load_project(args.project, HandoffProject if is_handoff else Project)
            collection = getattr(args, "environment_collection", None)
            if collection:
                if collection.stat().st_size > 2 * 1024 * 1024:
                    raise ValueError("Environment collection exceeds 2 MiB")
                project = EnvironmentCollection.model_validate_json(collection.read_text(encoding="utf-8-sig")).apply(project)
            if args.command == "validate":
                fields = {"motions", "movement"}
                report = preflight(project, workspace_for(args))
                result = report.model_dump(mode="json", exclude=fields if report.motions is None else None)
            elif args.command in {"navigation", "actions"}:
                result = compile_actions(project, workspace_for(args)).model_dump(mode="json",
                    exclude={"compiled_project"} if args.command == "navigation" else None)
            elif args.command == "production":
                operation = handoff_preview if is_handoff else preview
                result = operation(project, workspace_for(args), blender=args.blender).model_dump(mode="json")
            elif args.command == "verify":
                result = verify_video(args.video.resolve(), project.render, find_tool("ffprobe"), expect_audio=bool(project.audio))
            else:
                if args.engine:
                    project.render.engine = args.engine
                path = render_project(project, args.output, blender=args.blender, asset_library=args.asset_library,
                    audio_library=args.audio_library, asset_cache=args.asset_cache, motion_cache=args.motion_cache)
                result = {"status": "succeeded", "video": str(path), "manifest": str(path.parent / "manifest.json")}
        print(json.dumps(result, indent=2))
        if args.command == "assets" and args.asset_command == "batch" and result["status"] != "succeeded":
            return 2
        if args.command == "voice" and args.voice_command == "doctor" and not result.get("ready"):
            return 2
        return 0
    except KeyboardInterrupt:
        print(json.dumps({"error": "Production cancelled; completed files and job history retained"}), file=sys.stderr)
        return 130
    except ProductionError as exc:
        print(json.dumps({"code": exc.code, "error": str(exc)}), file=sys.stderr)
        return 2
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, sqlite3.Error) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
