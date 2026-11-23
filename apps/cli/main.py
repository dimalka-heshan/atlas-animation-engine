"""Small working production CLI. Standard output is machine-readable JSON."""
import argparse
import json
import logging
import sqlite3
import subprocess
import sys
from pathlib import Path

from engine import __version__
from engine.core.models import Project
from engine.rendering.pipeline import render_project
from engine.rendering.runtime import doctor, find_tool
from engine.rendering.video import verify_video
from engine.storage.jobs import list_jobs
from engine.worlds.placement import expand_project


class JsonFormatter(logging.Formatter):
    def format(self, record):
        data = {"level": record.levelname, "event": record.getMessage()}
        for key in ("job_id", "directory", "error"):
            if hasattr(record, key):
                data[key] = getattr(record, key)
        return json.dumps(data)


def load_project(path: Path) -> Project:
    if path.stat().st_size > 10_000_000:
        raise ValueError("Project JSON exceeds the 10 MB input limit")
    return Project.model_validate_json(path.read_text(encoding="utf-8-sig"))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="atlas", description="ATLAS local 3D animation production")
    root.add_argument("--version", action="version", version=__version__)
    sub = root.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="inspect runtime and installed executables")
    sub.add_parser("schema", help="print the project JSON Schema")
    validate = sub.add_parser("validate", help="validate a project and expand procedural placement")
    validate.add_argument("project", type=Path)
    render = sub.add_parser("render", help="render and verify a new production job")
    render.add_argument("project", type=Path)
    render.add_argument("--output", type=Path, default=Path("outputs"))
    render.add_argument("--blender", type=Path)
    render.add_argument("--engine", choices=["cycles", "eevee"])
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
        elif args.command == "jobs":
            result = list_jobs(args.output.resolve())
        else:
            project = load_project(args.project)
            if args.command == "validate":
                expanded = expand_project(project)
                result = {"valid": True, "project": project.id, "entities": len(expanded.scene.entities),
                          "frames": project.render.frames, "duration_seconds": project.render.frames / project.render.fps}
            elif args.command == "verify":
                result = verify_video(args.video.resolve(), project.render, find_tool("ffprobe"))
            else:
                if args.engine:
                    project.render.engine = args.engine
                path = render_project(project, args.output, blender=args.blender)
                result = {"status": "succeeded", "video": str(path), "manifest": str(path.parent / "manifest.json")}
        print(json.dumps(result, indent=2))
        return 0
    except KeyboardInterrupt:
        print(json.dumps({"error": "Production cancelled; completed files and job history retained"}), file=sys.stderr)
        return 130
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, sqlite3.Error) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
