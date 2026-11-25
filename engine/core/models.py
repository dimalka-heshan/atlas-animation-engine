"""Versioned Blender production IR. Units: meters, degrees, integer frames."""
from math import dist
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator
from engine.lipsync.models import LipSyncTimeline, FacialControls
from engine.core.quality import PRESETS

Number = Annotated[float, Field(allow_inf_nan=False, strict=True, ge=-1e9, le=1e9)]
Positive = Annotated[Number, Field(gt=0)]
Unit = Annotated[Number, Field(ge=0, le=1)]
Vec3 = tuple[Number, Number, Number]
Scale = tuple[Positive, Positive, Positive]
Color = tuple[Unit, Unit, Unit]
Identifier = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")]
Frame = Annotated[StrictInt, Field(ge=1)]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Material(Model):
    color: Color = (0.12, 0.48, 0.7)
    metallic: Unit = 0
    roughness: Unit = 0.4


class Keyframe(Model):
    frame: Frame
    location: Vec3 | None = None
    rotation: Vec3 | None = None
    scale: Scale | None = None


class AnimatedEntity(Model):
    id: Identifier
    location: Vec3 = (0, 0, 1)
    rotation: Vec3 = (0, 0, 0)
    scale: Scale = (1, 1, 1)
    interpolation: Literal["LINEAR", "BEZIER", "CONSTANT"] = "LINEAR"
    keyframes: list[Keyframe] = Field(default_factory=list, max_length=10000)


class Entity(AnimatedEntity):
    primitive: Literal["cube", "uv_sphere", "ico_sphere", "cylinder", "cone", "torus", "plane"] = "cube"
    material: Material = Field(default_factory=Material)
    bevel: Annotated[Number, Field(ge=0, le=0.5)] = 0.05
    smooth: bool = True


class CharacterEntity(AnimatedEntity):
    character: Literal["atlas-face-1"]


class AssetReference(Model):
    id: Identifier
    version: Annotated[StrictInt, Field(ge=1, le=9223372036854775807)]


class AssetEntity(AnimatedEntity):
    asset: AssetReference
    normalize: Literal["none", "unit"] = "none"
    pivot: Literal["origin", "center", "base"] = "origin"


class MotionPin(Model):
    id: Identifier
    sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class ClipEvent(Model):
    name: Annotated[str, Field(min_length=1, max_length=64)]
    start_frame: Frame
    frame_count: Frame
    speed: Annotated[Number, Field(ge=.1, le=4)] = 1
    loop: bool = False
    blend_frames: Annotated[StrictInt, Field(ge=0, le=120)] = 0
    blend_out_frames: Annotated[StrictInt, Field(ge=0, le=120)] = 0
    motion: MotionPin | None = None
    overlay: bool = False


class RiggedEntity(AssetEntity):
    rigged: Literal[True]
    clips: list[ClipEvent] = Field(default_factory=list, max_length=128)
    equipment: dict[Literal["left_hand", "right_hand"], Identifier] = Field(default_factory=dict)


Rectangle = tuple[Number, Number, Number, Number]


class Navigation(Model):
    bounds: Rectangle
    obstacles: list[Rectangle] = Field(default_factory=list, max_length=64)
    clearance: Annotated[Number, Field(ge=0, le=4)] = .28
    actor_separation: Annotated[Number, Field(ge=.1, le=8)] = .55


class MovementAction(Model):
    actor: Identifier
    kind: Literal["walk_to", "run_to", "follow_waypoints", "approach_actor"]
    motion: MotionPin
    destination: Vec3 | None = None
    waypoints: list[Vec3] = Field(default_factory=list, max_length=32)
    target_actor: Identifier | None = None
    stop_distance: Annotated[Number, Field(ge=.1, le=20)] = 1
    speed_mps: Annotated[Number, Field(ge=.25, le=8)] | None = None
    start_frame: Frame = 1
    blend_frames: Annotated[StrictInt, Field(ge=0, le=30)] = 4

    @model_validator(mode="after")
    def one_destination(self) -> Self:
        expected = {"walk_to": "destination", "run_to": "destination", "follow_waypoints": "waypoints",
                    "approach_actor": "target_actor"}[self.kind]
        fields = {key for key, value in (("destination", self.destination), ("waypoints", self.waypoints),
                                        ("target_actor", self.target_actor)) if value is not None and value != []}
        if fields != {expected} or self.target_actor == self.actor:
            raise ValueError(f"{self.kind} requires exactly its own destination or another actor")
        return self


class EnvironmentCollection(Model):
    schema_version: Literal["1.0"] = "1.0"
    id: Identifier
    entities: list[AssetEntity] = Field(min_length=1, max_length=1000)

    def apply(self, project: "Project") -> "Project":
        if project.schema_version not in {"1.3", "1.4", "1.5"}:
            raise ValueError("Environment collections require project schema_version 1.3 or later")
        data = project.model_dump(mode="json")
        data["scene"]["entities"].extend(entity.model_dump(mode="json") for entity in self.entities)
        return Project.model_validate(data)


class Camera(Model):
    location: Vec3 = (8, -10, 7)
    target: Vec3 = (0, 0, 1)
    target_entity: Identifier | None = None
    lens: Annotated[Number, Field(ge=10, le=300)] = 45
    keyframes: list[Keyframe] = Field(default_factory=list, max_length=10000)
    interpolation: Literal["LINEAR", "BEZIER", "CONSTANT"] = "LINEAR"
    depth_of_field: bool = False
    fstop: Annotated[Number, Field(ge=0.7, le=64)] = 5.6


class Light(Model):
    id: Identifier = "key"
    kind: Literal["AREA", "SUN", "POINT"] = "AREA"
    location: Vec3 = (3, -4, 7)
    target: Vec3 = (0, 0, 0)
    color: Color = (1, 0.9, 0.78)
    energy: Annotated[Number, Field(ge=0, le=1000000)] = 1200
    size: Annotated[Number, Field(gt=0, le=1000)] = 5
    temperature_kelvin: Annotated[Number, Field(ge=1000, le=20000)] | None = None
    cast_shadows: bool | None = None

    @model_validator(mode="after")
    def directional_target(self) -> Self:
        if self.kind != "POINT" and dist(self.location, self.target) < 1e-8:
            raise ValueError("directional light location must differ from target")
        return self


class Environment(Model):
    background: Color = (0.04, 0.06, 0.1)
    strength: Annotated[Number, Field(ge=0, le=10)] = 0.4
    ground: bool = True
    ground_size: Annotated[Number, Field(gt=0, le=10000)] = 200
    ground_material: Material = Field(default_factory=lambda: Material(color=(0.075, 0.1, 0.14), roughness=0.8))
    hdri: "EnvironmentMedia | None" = None
    ground_texture: "EnvironmentMedia | None" = None
    texture_repeats_per_meter: Annotated[Number, Field(gt=0, le=100)] = 1


class EnvironmentMedia(Model):
    id: Annotated[str, Field(pattern=r"^(?:polyhaven-[a-z0-9_]{1,80}|ambientcg-[a-z0-9]{1,80})$")]
    fingerprint: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class Scatter(Model):
    id: Identifier
    prototype: Entity | AssetEntity
    count: Annotated[StrictInt, Field(ge=0, le=5000)]
    bounds: tuple[Number, Number, Number, Number] = (-5, 5, -5, 5)
    scale_range: tuple[Positive, Positive] = (0.5, 1.5)
    min_distance: Annotated[Number, Field(ge=0)] = 0

    @model_validator(mode="after")
    def valid_ranges(self) -> Self:
        x0, x1, y0, y1 = self.bounds
        if x0 >= x1 or y0 >= y1 or self.scale_range[0] > self.scale_range[1]:
            raise ValueError("scatter bounds and scale_range must be ordered")
        if self.prototype.keyframes:
            raise ValueError("scatter prototypes must be static; animate explicit entities")
        return self


class Scene(Model):
    entities: list[RiggedEntity | Entity | AssetEntity | CharacterEntity] = Field(default_factory=list, max_length=10000)
    scatter: list[Scatter] = Field(default_factory=list, max_length=100)
    environment: Environment = Field(default_factory=Environment)
    camera: Camera = Field(default_factory=Camera)
    lights: list[Light] = Field(default_factory=lambda: [Light()], max_length=100)


class RenderSettings(Model):
    engine: Literal["cycles", "eevee"] = "cycles"
    width: Annotated[StrictInt, Field(ge=16, le=7680)] = 320
    height: Annotated[StrictInt, Field(ge=16, le=7680)] = 180
    fps: Annotated[StrictInt, Field(ge=1, le=120)] = 24
    frames: Annotated[StrictInt, Field(ge=1, le=100000)] = 48
    samples: Annotated[StrictInt, Field(ge=1, le=4096)] = 16
    threads: Annotated[StrictInt, Field(ge=1, le=128)] = 8
    timeout_seconds: Annotated[StrictInt, Field(ge=10, le=604800)] = 3600

    @model_validator(mode="after")
    def even_dimensions(self) -> Self:
        if self.width % 2 or self.height % 2:
            raise ValueError("H.264 yuv420p requires even width and height")
        return self


class QualitySettings(Model):
    profile: Literal["preview", "stylized", "realistic", "cinematic"]
    look: Literal["None", "AgX - Medium High Contrast", "AgX - Medium Low Contrast"] | None = None
    exposure: Annotated[Number, Field(ge=-5, le=5)] = 0
    motion_blur: bool = False
    denoise: bool = True
    max_asset_polygons: Annotated[StrictInt, Field(ge=1, le=20_000_000)] = 2_000_000
    max_texture_size: Literal[1024, 2048, 4096, 8192] = 4096


class Project(Model):
    schema_version: Literal["1.0", "1.1", "1.2", "1.3", "1.4", "1.5"] = "1.0"
    id: Identifier
    seed: Annotated[StrictInt, Field(ge=0, le=2147483647)] = 1
    scene: Scene
    render: RenderSettings = Field(default_factory=RenderSettings)
    audio: list["AudioEvent"] = Field(default_factory=list, max_length=100)
    performances: list["FacialPerformance"] = Field(default_factory=list, max_length=100)
    quality: QualitySettings | None = None
    navigation: Navigation | None = None
    actions: list[MovementAction] = Field(default_factory=list, max_length=32)

    @model_validator(mode="before")
    @classmethod
    def preset_defaults(cls, data):
        if not isinstance(data, dict) or not isinstance(data.get("quality"), dict):
            return data
        quality = data["quality"]
        profile = quality.get("profile")
        preset = PRESETS.get(profile) if isinstance(profile, str) else None
        if preset is None or not isinstance(data.get("render", {}), dict):
            return data
        settings = {key: preset[key] for key in ("engine", "width", "height", "samples")}
        return data | {"quality": {"look": preset["look"]} | quality, "render": settings | data.get("render", {})}

    @model_validator(mode="after")
    def validate_scene(self) -> Self:
        if self.quality is not None and self.schema_version not in {"1.4", "1.5"}:
            raise ValueError("Production quality profiles require schema 1.4")
        if self.schema_version not in {"1.4", "1.5"} and any(
                light.temperature_kelvin is not None or light.cast_shadows is not None for light in self.scene.lights):
            raise ValueError("Light temperature and shadow overrides require schema 1.4")
        if (self.scene.environment.hdri or self.scene.environment.ground_texture) and self.schema_version not in {"1.3", "1.4", "1.5"}:
            raise ValueError("Acquired environment media require schema_version 1.3 or later")
        if self.audio and self.schema_version not in {"1.2", "1.3", "1.4", "1.5"}:
            raise ValueError("Audio requires schema_version 1.2 or later")
        characters = {entity.id for entity in self.scene.entities if isinstance(entity, CharacterEntity)}
        if (characters or self.performances) and self.schema_version not in {"1.2", "1.3", "1.4", "1.5"}:
            raise ValueError("Characters and facial performances require schema_version 1.2 or later")
        static_ids = {e.id for e in self.scene.entities if type(e) is AssetEntity}
        attached = set()
        actors = {e.id: e for e in self.scene.entities if isinstance(e, RiggedEntity)}
        if (self.navigation or self.actions) and self.schema_version != "1.5":
            raise ValueError("Navigation and movement actions require schema 1.5")
        if self.actions and not self.navigation:
            raise ValueError("Movement actions require explicit navigation bounds")
        if len({action.actor for action in self.actions}) != len(self.actions):
            raise ValueError("Use one movement action per actor")
        for action in self.actions:
            actor = actors.get(action.actor)
            if actor is None or (action.target_actor and action.target_actor not in actors):
                raise ValueError("Movement actions require explicit rigged actors")
            if actor.keyframes or actor.clips or actor.normalize != "none" or actor.pivot != "base" or actor.scale != (1, 1, 1):
                raise ValueError("Movement requires a meter-scale, base-pivot actor with no manual clips or keys")
        for actor in actors.values():
            if self.schema_version not in {"1.3", "1.4", "1.5"}:
                raise ValueError("Rigged assets require schema_version 1.3 or later")
            for equipment in actor.equipment.values():
                if equipment not in static_ids or equipment in attached:
                    raise ValueError("Equipment must reference a unique explicit static asset entity")
                attached.add(equipment)
            last = {False: 1, True: 1}
            base_clips = []
            for clip in actor.clips:
                end = clip.start_frame + clip.frame_count
                if (clip.motion or clip.overlay or clip.blend_out_frames) and self.schema_version != "1.5":
                    raise ValueError("Motion pins and overlay blends require schema 1.5")
                if (clip.start_frame < last[clip.overlay] or end > self.render.frames + 1
                        or clip.blend_frames + clip.blend_out_frames >= clip.frame_count):
                    raise ValueError("Clip events must be ordered, nonoverlapping and within render frames")
                if clip.overlay:
                    if not clip.motion or not any(begin <= clip.start_frame and end <= finish for begin, finish in base_clips):
                        raise ValueError("A motion overlay requires an earlier base strip covering its entire interval")
                else:
                    if last[True] != 1:
                        raise ValueError("Base clips must precede motion overlays")
                    base_clips.append((clip.start_frame, end))
                last[clip.overlay] = end
        if self.audio and self.render.frames / self.render.fps > 180:
            raise ValueError("This audio production profile supports at most 180 seconds")
        if len({event.id for event in self.audio}) != len(self.audio):
            raise ValueError("Audio event identifiers must be unique")
        if any(event.start_seconds >= self.render.frames / self.render.fps for event in self.audio):
            raise ValueError("Audio event starts outside the video duration")
        events = {event.id: event for event in self.audio}
        active: dict[str, list[tuple[float, float]]] = {}
        for performance in self.performances:
            if performance.profile == "mpfb-visemes-1":
                if self.schema_version not in {"1.4", "1.5"} or performance.actor_id not in actors or performance.controls is not None:
                    raise ValueError("MPFB facial performances require schema 1.4 and a pinned compatible rigged actor")
                blinks = performance.blink_frames
                if any(frame < 2 or frame >= self.render.frames for frame in blinks) or any(
                        second - first < 2 for first, second in zip(blinks, blinks[1:])):
                    raise ValueError("Blink frames must be inside the rendered interval and at least two frames apart")
            elif performance.actor_id not in characters or performance.blink_frames:
                raise ValueError("Facial actor must reference a compatible character, not a static asset")
            event = events.get(performance.audio_event_id)
            if event is None or event.role != "dialogue" or event.speaker != performance.actor_id:
                raise ValueError("Facial performance requires a dialogue event assigned to the same speaker")
            interval = (event.start_seconds, event.start_seconds + performance.timeline.duration_seconds)
            if interval[1] > self.render.frames / self.render.fps + 1e-8:
                raise ValueError("Facial performance extends beyond video duration")
            if any(interval[0] < end and interval[1] > start for start, end in active.get(performance.actor_id, [])):
                raise ValueError("One actor cannot have overlapping facial performances")
            active.setdefault(performance.actor_id, []).append(interval)
        prototypes = [*self.scene.entities, *(group.prototype for group in self.scene.scatter)]
        if self.schema_version == "1.0" and any(isinstance(entity, AssetEntity) for entity in prototypes):
            raise ValueError("Asset references require schema_version 1.1")
        ids = [entity.id for entity in self.scene.entities]
        generated = [f"{group.id}_{i}" for group in self.scene.scatter for i in range(group.count)]
        all_ids = ids + generated + [light.id for light in self.scene.lights]
        if len(all_ids) != len(set(all_ids)):
            raise ValueError("entity, generated and light identifiers must be unique")
        if any(len(identifier) > 64 for identifier in generated):
            raise ValueError("scatter identifier too long for generated entity IDs")
        if len(ids) + len(generated) > 10000:
            raise ValueError("scene exceeds 10000 entities")
        camera = self.scene.camera
        if camera.target_entity and camera.target_entity not in ids:
            raise ValueError("camera target_entity must reference an explicit entity")
        if not camera.target_entity:
            positions = [camera.location, *(key.location for key in camera.keyframes if key.location is not None)]
            if any(dist(position, camera.target) < 1e-8 for position in positions):
                raise ValueError("camera location and location keys must differ from target")
        for animated in [*self.scene.entities, camera]:
            frames = [key.frame for key in animated.keyframes]
            if frames != sorted(set(frames)):
                raise ValueError("keyframes must have unique, increasing frame numbers")
            if frames and frames[-1] > self.render.frames:
                raise ValueError("keyframe exceeds render frame range")
            if any(k.location is None and k.rotation is None and k.scale is None for k in animated.keyframes):
                raise ValueError("keyframe must change at least one transform")
        if any(k.rotation is not None or k.scale is not None for k in camera.keyframes):
            raise ValueError("tracked cameras support location keyframes only")
        return self


class AudioEvent(Model):
    id: Identifier
    clip: AssetReference
    role: Literal["narration", "dialogue"] = "narration"
    start_seconds: Annotated[Number, Field(ge=0, le=86400)] = 0
    gain: Annotated[Number, Field(gt=0, le=1)] = 1
    speaker: Identifier | None = None


class FacialPerformance(Model):
    actor_id: Identifier
    audio_event_id: Identifier
    timeline: LipSyncTimeline
    profile: Literal["atlas-face-1", "mpfb-visemes-1"] = "atlas-face-1"
    blink_frames: list[Frame] = Field(default_factory=list, max_length=100)
    controls: FacialControls | None = None
    smoothing_seconds: Annotated[Number, Field(ge=0, le=.2)] = .04


Project.model_rebuild()
