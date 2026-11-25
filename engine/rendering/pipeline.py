"""Production orchestration; success is recorded only after artifact verification."""
import hashlib
import importlib.metadata
import json
import logging
import platform
import time
import uuid
from pathlib import Path

from engine import __version__
from engine.assets.resolution import resolve_project_assets, snapshot_assets
from engine.assets.environment_media import resolve_media, snapshot_media
from engine.audio.production import resolve_audio, snapshot_audio, mix_audio, mux_audio
from engine.core.models import Project
from engine.core.quality import enforce_geometry_budget
from engine.rendering.runtime import capture, find_tool, run_logged
from engine.rendering.video import encode_video, verify_video
from engine.storage.jobs import JobStore, atomic_json, contained_path, utc_now
from engine.worlds.placement import expand_project

LOG = logging.getLogger("atlas")


def source_digest() -> str:
    digest = hashlib.sha256()
    for path in sorted(Path(__file__).resolve().parents[1].rglob("*.py")):
        digest.update(path.relative_to(Path(__file__).resolve().parents[1]).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def render_project(project: Project, output_root: Path, *, blender: Path | None = None,
                   ffmpeg: Path | None = None, ffprobe: Path | None = None,
                   asset_library: Path | None = None, audio_library: Path | None = None,
                   asset_cache: Path | None = None) -> Path:
    """Render into a new job directory inside an explicitly approved output root.

    Returns the verified MP4 path; errors retain the project, logs and failed status.
    No scene-supplied commands, imports or filesystem paths are executed.
    """
    # Nested models/lists may have been modified by an API caller after validation.
    project = Project.model_validate(project.model_dump(mode="json"))
    started = time.perf_counter()
    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    job_id = uuid.uuid4().hex
    directory = contained_path(output_root, f"{project.id}-{job_id}")
    directory.mkdir()
    store = JobStore(contained_path(output_root, "jobs.sqlite3"))
    store.create(job_id, project.id, directory)
    manifest = {"job_id": job_id, "project_id": project.id, "status": "running",
                "created_at": utc_now(), "engine_version": __version__,
                "seed": project.seed, "timings_seconds": {}, "assets": [],
                "render_settings": project.render.model_dump(mode="json")}
    try:
        atomic_json(directory / "manifest.json", manifest)
        manifest.update(engine_source_sha256=source_digest(), python=platform.python_version(),
                        platform=platform.platform(),
                        dependencies={"pydantic": importlib.metadata.version("pydantic")})
        atomic_json(directory / "project.json", project.model_dump(mode="json"))
        manifest["project_sha256"] = hashlib.sha256((directory / "project.json").read_bytes()).hexdigest()
        expanded = expand_project(project)
        entries = resolve_project_assets(expanded, asset_library or Path("assets/library"))
        enforce_geometry_budget(expanded, entries)
        if project.quality:
            manifest["quality"] = project.quality.model_dump(mode="json")
        manifest["assets"] = snapshot_assets(entries, directory)
        cache = asset_cache or Path("assets/acquisition")
        manifest["environment_media"] = snapshot_media(resolve_media(expanded, cache), cache, directory)
        audio_entries = resolve_audio(expanded, audio_library or Path("assets/audio"))
        manifest["audio"] = snapshot_audio(audio_entries, directory)
        atomic_json(directory / "resolved.json", expanded.model_dump(mode="json"))
        executables = {"blender": find_tool("blender", blender), "ffmpeg": find_tool("ffmpeg", ffmpeg),
                       "ffprobe": find_tool("ffprobe", ffprobe)}
        manifest["tools"] = {name: {"path": str(path), "version": capture([str(path),
            "--version" if name == "blender" else "-version"]).splitlines()[0]} for name, path in executables.items()}
        if audio_entries:
            manifest["audio_mix"] = mix_audio(manifest["audio"], directory, project.render.frames / project.render.fps,
                executables["ffmpeg"], project.render.timeout_seconds)
        atomic_json(directory / "manifest.json", manifest)
        worker = Path(__file__).resolve().parents[1] / "adapters" / "blender" / "worker.py"
        (directory / "frames").mkdir()
        LOG.info("render_started", extra={"job_id": job_id, "directory": str(directory)})
        manifest["timings_seconds"]["blender_process"] = run_logged([
            str(executables["blender"]), "--background", "--factory-startup", "--disable-autoexec",
            "--threads", str(project.render.threads), "--python-exit-code", "1", "--python", str(worker),
            "--", str(directory / "resolved.json"), str(directory)],
            directory / "blender.log", project.render.timeout_seconds)
        for frame in range(1, project.render.frames + 1):
            image = directory / "frames" / f"{frame:06d}.png"
            if not image.is_file() or image.stat().st_size < 50:
                raise RuntimeError(f"Missing or empty rendered frame: {image}")
        manifest["blender"] = json.loads((directory / "blender-report.json").read_text(encoding="utf-8"))
        manifest["timings_seconds"]["encoding"] = encode_video(directory, project.render, executables["ffmpeg"])
        if audio_entries:
            manifest["timings_seconds"]["audio_mux"] = mux_audio(directory, project.render.frames / project.render.fps,
                executables["ffmpeg"], project.render.timeout_seconds)
        manifest["video"] = verify_video(directory / "video.partial.mp4", project.render, executables["ffprobe"],
            expect_audio=bool(audio_entries))
        # Decode every frame: metadata alone cannot prove that a stream is intact.
        manifest["timings_seconds"]["decode_verification"] = run_logged([
            str(executables["ffmpeg"]), "-nostdin", "-v", "error", "-xerror", "-i",
            str(directory / "video.partial.mp4"), "-f", "null", "-"],
            directory / "verification.log", project.render.timeout_seconds)
        (directory / "video.partial.mp4").replace(directory / "video.mp4")
        with (directory / "video.mp4").open("rb") as handle:
            manifest["video"]["sha256"] = hashlib.file_digest(handle, "sha256").hexdigest()
        manifest["disk_bytes"] = sum(p.stat().st_size for p in directory.rglob("*") if p.is_file())
        manifest["status"] = "succeeded"
        manifest["finished_at"] = utc_now()
        manifest["timings_seconds"]["total"] = time.perf_counter() - started
        atomic_json(directory / "manifest.json", manifest)
        store.update(job_id, "succeeded")
        LOG.info("render_succeeded", extra={"job_id": job_id})
        return directory / "video.mp4"
    except BaseException as exc:
        manifest["status"] = "cancelled" if isinstance(exc, KeyboardInterrupt) else "failed"
        manifest["error"] = f"{type(exc).__name__}: {exc}"
        # Preserve the original error even if the disk/database also fails during cleanup.
        for operation in (
            lambda: store.update(job_id, manifest["status"], manifest["error"]),
            lambda: atomic_json(directory / "manifest.json", manifest),
        ):
            try:
                manifest["finished_at"] = utc_now()
                manifest["timings_seconds"]["total"] = time.perf_counter() - started
                operation()
            except Exception as persistence_error:
                LOG.error("failure_persistence_error", extra={"job_id": job_id, "error": str(persistence_error)})
        LOG.error("render_failed", extra={"job_id": job_id, "error": str(exc)})
        raise
