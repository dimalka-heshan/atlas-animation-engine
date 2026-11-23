"""Versioned renderer-independent IR. Units: meters, degrees, integer frames."""
from math import dist
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

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


class AssetReference(Model):
    id: Identifier
    version: Annotated[StrictInt, Field(ge=1, le=9223372036854775807)]


class AssetEntity(AnimatedEntity):
    asset: AssetReference
    normalize: Literal["none", "unit"] = "none"
    pivot: Literal["origin", "center", "base"] = "origin"


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
    entities: list[Entity | AssetEntity] = Field(default_factory=list, max_length=10000)
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


class Project(Model):
    schema_version: Literal["1.0", "1.1"] = "1.0"
    id: Identifier
    seed: Annotated[StrictInt, Field(ge=0, le=2147483647)] = 1
    scene: Scene
    render: RenderSettings = Field(default_factory=RenderSettings)

    @model_validator(mode="after")
    def validate_scene(self) -> Self:
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
