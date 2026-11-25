"""Shared host-side production and model-independent director contracts."""
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from engine import __version__
from engine.assets.environment_media import resolve_media
from engine.assets.resolution import resolve_project_assets
from engine.audio.production import resolve_audio
from engine.characters.interaction import validate_handoff
from engine.characters.locomotion import compile_movement
from engine.characters.motion import resolve_motions
from engine.core.models import AssetReference, Model, MotionPin, Project, PropHandoff
from engine.core.quality import enforce_geometry_budget
from engine.worlds.placement import expand_project


CapabilityName = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$", max_length=100)]
Text = Annotated[str, StringConstraints(min_length=1, max_length=4000, strip_whitespace=True)]


@dataclass(frozen=True)
class ProductionWorkspace:
    """Trusted runtime configuration supplied by the host, outside director inputs."""

    output: Path = Path("outputs")
    asset_library: Path = Path("assets/library")
    asset_cache: Path = Path("assets/acquisition")
    audio_library: Path = Path("assets/audio")
    motion_cache: Path = Path("assets/motions")


@dataclass(frozen=True)
class PreparedScene:
    project: Project
    movement: list[dict]
    assets: list[dict]
    motions: dict


class ProductionError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class CreativePlan(Model):
    schema_version: Literal["1.0"]
    title: Text
    summary: Text
    genre: Text | None = None
    audience: Text | None = None
    visual_style: Text | None = None
    duration_seconds: Annotated[float, Field(gt=0, le=86400)] | None = None
    aspect_ratio: Literal["16:9", "9:16", "1:1", "2.39:1"] | None = None
    characters: list[Text] = Field(default_factory=list, max_length=64)
    locations: list[Text] = Field(default_factory=list, max_length=64)
    beats: list[Text] = Field(default_factory=list, max_length=100)
    scene_intents: list[Text] = Field(default_factory=list, max_length=100)
    dialogue_intents: list[Text] = Field(default_factory=list, max_length=100)
    narration_intents: list[Text] = Field(default_factory=list, max_length=100)
    shot_intents: list[Text] = Field(default_factory=list, max_length=100)
    performance_intent: Text | None = None
    camera_intent: Text | None = None
    lighting_intent: Text | None = None
    sound_intent: Text | None = None
    asset_requirements: list[Text] = Field(default_factory=list, max_length=100)
    quality_requirements: list[Text] = Field(default_factory=list, max_length=100)
    required_capabilities: list[CapabilityName] = Field(default_factory=list, max_length=100)


class ProductionGap(Model):
    capability: CapabilityName
    code: Literal["unknown_capability", "unavailable_capability"]
    message: str


class CreativePlanReview(Model):
    ready: bool
    gaps: list[ProductionGap]


class ResolvedAsset(AssetReference):
    sha256: str


class MovementEvidence(Model):
    actor: str
    kind: str
    motion: MotionPin
    points: list[tuple[float, float]]
    frames: list[int]
    distance_m: float
    speed_mps: float
    playback: float
    facing: tuple[float, float] | None
    stop_distance_m: float | None


class PreflightResult(Model):
    valid: Literal[True] = True
    project: str
    entities: int
    frames: int
    duration_seconds: float
    assets: list[ResolvedAsset]
    audio_events: int
    environment_media: int
    motions: int | None = None
    movement: list[MovementEvidence] | None = None


class CompilationResult(Model):
    project: str
    movement: list[MovementEvidence]
    compiled_project: Project


class PreviewResult(Model):
    status: Literal["succeeded"] = "succeeded"
    video: Path
    manifest: Path


class HandoffProject(Project):
    schema_version: Literal["1.6"] = "1.6"
    handoff: PropHandoff


class HandoffResult(PreviewResult):
    handoff_report: Path


class Capability(Model):
    name: CapabilityName
    description: str
    version: Literal["1.0"] = "1.0"
    status: Literal["implemented", "experimental", "unavailable"]
    input_schema: dict | None = None
    output_schema: dict | None = None
    command: str | None = None
    required_assets: list[str] = Field(default_factory=list)
    supported_rigs: list[str] = Field(default_factory=list)
    supported_environments: list[str] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    requires_authentication: bool = False
    costly_render: bool = False
    artifacts: list[str] = Field(default_factory=list)


class CapabilityCatalog(Model):
    schema_version: Literal["1.0"] = "1.0"
    engine_version: str
    capabilities: list[Capability]


PREVIEW_LIMITS = {"long_edge": 960, "short_edge": 540, "frames": 240, "samples": 32, "threads": 16}


def _capability(name, description, request, response, command, **metadata):
    return Capability(name=name, description=description, status="implemented", command=command,
                      input_schema=request.model_json_schema(), output_schema=response.model_json_schema(), **metadata)


def capabilities() -> CapabilityCatalog:
    return CapabilityCatalog(engine_version=__version__, capabilities=[
        _capability("project.validate", "Resolve a project against approved local inputs.", Project, PreflightResult,
                    "atlas validate", required_assets=["Pinned assets, motion and audio when referenced"],
                    supported_rigs=["Inspected source GLB rigs", "MPFB game-engine"],
                    supported_environments=["Primitive scenes", "Inspected static collections", "Pinned environment media"]),
        _capability("actions.compile", "Compile bounded locomotion into editable transform and clip tracks.",
                    Project, CompilationResult, "atlas actions compile",
                    required_assets=["Pinned target human and compatible motion for each action"],
                    supported_rigs=["MPFB game-engine"], supported_environments=["Declared flat-ground navigation"],
                    limitations=["One route per actor", "Explicit static obstacles", "No runtime replanning"]),
        _capability("render.preview", "Render and verify a bounded Blender preview.", Project, PreviewResult,
                    "atlas production preview", costly_render=True,
                    required_assets=["Pinned assets, media, audio and motion when referenced"],
                    supported_rigs=["Inspected source GLB rigs", "MPFB game-engine"],
                    supported_environments=["Primitive scenes", "Inspected static collections", "Pinned environment media"],
                    preconditions=["Blender and FFmpeg/ffprobe installed"],
                    limitations=["Single project", "960 by 540 maximum, either orientation", "240 frames", "32 samples", "16 threads"],
                    artifacts=["video.mp4", "manifest.json", "scene.blend", "Numbered PNG frames"]),
        _capability("director.validate_plan", "Validate intent and return capability gaps without executing.",
                    CreativePlan, CreativePlanReview, "atlas director validate", limitations=["Intent intake only"]),
        _capability("props.transfer", "Reach, transfer and release one declared prop between two arrived actors.",
                    HandoffProject, HandoffResult, "atlas production handoff", costly_render=True,
                    required_assets=["Two approved MPFB actors", "One static prop or configured primitive"],
                    supported_rigs=["MPFB game-engine"], supported_environments=["Stationary interaction stage"],
                    preconditions=["Schema 1.6 handoff", "Declared initial owner and grip anchors", "Both actors within arm reach"],
                    limitations=["Wrist position constraints", "Fixed prop orientation", "One transfer per shot"],
                    artifacts=["video.mp4", "scene.blend", "handoff-report.json", "manifest.json"]),
        Capability(name="motion.walk_contact", description="Stabilize sampled ankles on flat-ground walking clips.",
                   status="experimental", command="atlas production preview", costly_render=True,
                   input_schema=Project.model_json_schema(), output_schema=PreviewResult.model_json_schema(),
                   supported_rigs=["MPFB game-engine"], supported_environments=["Z=0 ground plane"],
                   preconditions=["Schema 1.6 foot_lock", "Pinned grounded walking bake"],
                   limitations=["Partial slide correction", "Excludes running and terrain"],
                   artifacts=["foot-contact-report.json", "scene.blend", "manifest.json"]),
        Capability(name="world.generate", description="Generate a persistent procedural world.", status="unavailable"),
        Capability(name="timeline.assemble", description="Assemble multiple shots into a cinematic timeline.", status="unavailable"),
        Capability(name="director.compile_story", description="Resolve creative intent into executable production.", status="unavailable"),
        Capability(name="director.mcp", description="Serve production operations to MCP clients.", status="unavailable"),
    ])


def validate_creative_plan(plan: CreativePlan) -> CreativePlanReview:
    statuses = {item.name: item.status for item in capabilities().capabilities}
    gaps = []
    for name in dict.fromkeys(plan.required_capabilities):
        if name not in statuses:
            gaps.append(ProductionGap(capability=name, code="unknown_capability", message="No capability exists with that name."))
        elif statuses[name] == "unavailable":
            gaps.append(ProductionGap(capability=name, code="unavailable_capability", message="This operation is unavailable in the installed engine."))
    return CreativePlanReview(ready=not gaps, gaps=gaps)


def prepare_scene(project: Project, workspace: ProductionWorkspace) -> PreparedScene:
    motions = resolve_motions(project, workspace.motion_cache)
    expanded, plans = compile_movement(expand_project(project), motions)
    assets = resolve_project_assets(expanded, workspace.asset_library, motions, movement_actions=project.actions)
    enforce_geometry_budget(expanded, assets)
    validate_handoff(expanded, assets)
    return PreparedScene(expanded, plans, assets, motions)


def preflight(project: Project, workspace: ProductionWorkspace) -> PreflightResult:
    prepared = prepare_scene(project, workspace)
    audio = resolve_audio(prepared.project, workspace.audio_library)
    media = resolve_media(prepared.project, workspace.asset_cache)
    assets = [ResolvedAsset(id=entry["id"], version=entry["version"], sha256=entry["sha256"]) for entry in prepared.assets]
    return PreflightResult(project=project.id, entities=len(prepared.project.scene.entities), frames=project.render.frames,
        duration_seconds=project.render.frames / project.render.fps, assets=assets, audio_events=len(audio),
        environment_media=len(media), motions=len(prepared.motions) if prepared.motions else None,
        movement=[MovementEvidence.model_validate(plan) for plan in prepared.movement] if prepared.motions else None)


def compile_actions(project: Project, workspace: ProductionWorkspace) -> CompilationResult:
    prepared = prepare_scene(project, workspace)
    return CompilationResult(project=project.id, compiled_project=prepared.project,
                             movement=[MovementEvidence.model_validate(plan) for plan in prepared.movement])


def preview(project: Project, workspace: ProductionWorkspace, *, blender: Path | None = None) -> PreviewResult:
    from engine.rendering.pipeline import render_project

    settings = project.render
    short, long = sorted((settings.width, settings.height))
    limits = PREVIEW_LIMITS
    if (long > limits["long_edge"] or short > limits["short_edge"] or settings.frames > limits["frames"]
            or settings.samples > limits["samples"] or settings.threads > limits["threads"]):
        raise ProductionError("preview_budget", "The preview exceeds its dimension, frame, sample or thread limit.")
    path = render_project(project, workspace.output, blender=blender, asset_library=workspace.asset_library,
                          asset_cache=workspace.asset_cache, audio_library=workspace.audio_library,
                          motion_cache=workspace.motion_cache)
    return PreviewResult(video=path, manifest=path.parent / "manifest.json")


def handoff_preview(project: Project, workspace: ProductionWorkspace, *, blender: Path | None = None) -> HandoffResult:
    if project.handoff is None:
        raise ProductionError("handoff_required", "Supply a schema 1.6 project with a declared handoff.")
    result = preview(project, workspace, blender=blender)
    return HandoffResult(video=result.video, manifest=result.manifest, handoff_report=result.video.parent / "handoff-report.json")
