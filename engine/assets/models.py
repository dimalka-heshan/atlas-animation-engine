"""Declared provenance and deliberately narrow render-usage policy."""
import re
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator

from engine.core.models import Model, Number

Text = Annotated[str, Field(max_length=20000)]


class Provenance(Model):
    name: Annotated[str, Field(min_length=1, max_length=200)]
    creator: Text
    source_url: Text
    license_id: Annotated[str, Field(min_length=1, max_length=100)]
    license_text: Annotated[str, Field(max_length=200000)]
    approval: Literal["unreviewed", "approved", "rejected"] = "unreviewed"
    render_allowed: StrictBool = False
    redistribution_allowed: StrictBool = False
    attribution: Text = ""
    restrictions: list[Text] = Field(default_factory=list, max_length=50)
    description: Text = ""
    category: Annotated[str, Field(min_length=1, max_length=100)] = "prop"
    tags: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def normalize_tags(self) -> Self:
        # Avoid assignment validation recursion; normalize only this one field.
        object.__setattr__(self, "tags", sorted(set(tag.casefold() for tag in self.tags)))
        return self

    def require_render_rights(self) -> None:
        """Enforce declared approval; this does not independently prove ownership."""
        if self.approval != "approved" or not self.render_allowed:
            raise ValueError("Asset must be explicitly approved with render_allowed=true")
        if self.license_id not in {"CC0-1.0", "CC-BY-4.0", "LicenseRef-ATLAS-Generated"}:
            raise ValueError(f"Unsupported or unknown asset license: {self.license_id}")
        if not all(value.strip() for value in (self.creator, self.source_url, self.license_text)):
            raise ValueError("Approved assets require creator, source URL and exact license text")
        source = urlsplit(self.source_url)
        valid_url = source.scheme in {"https", "http"} and bool(source.hostname) and not any(c.isspace() for c in self.source_url)
        valid_urn = bool(re.fullmatch(r"urn:[A-Za-z0-9][A-Za-z0-9-]{0,31}:[^\s]+", self.source_url))
        if not (valid_url or valid_urn):
            raise ValueError("Source URL requires an HTTP(S) host or a URN namespace and resource identifier")
        if self.license_id == "CC-BY-4.0" and not self.attribution.strip():
            raise ValueError("CC-BY-4.0 requires a non-empty attribution statement")
        if self.restrictions:
            raise ValueError("Assets with additional usage restrictions require a future policy implementation")


class InspectionProof(BaseModel):
    """Required evidence for readiness; full diagnostic report remains retained."""
    model_config = ConfigDict(extra="ignore")
    source_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    inspection_profile: Literal["atlas-static-glb-1", "atlas-pbr-glb-1", "atlas-rigged-glb-1", "atlas-human-glb-1"]
    blender_version: Annotated[str, Field(min_length=1)]
    mesh_count: Annotated[StrictInt, Field(ge=1)]
    polygon_count: Annotated[StrictInt, Field(ge=1)]
    dimensions: tuple[Number, Number, Number]
    missing_textures: list[str]

    @model_validator(mode="after")
    def renderable(self) -> Self:
        if min(self.dimensions) < 0 or max(self.dimensions) < 1e-8 or self.missing_textures:
            raise ValueError("Inspection must show renderable bounds without missing textures")
        return self


class ThumbnailProof(BaseModel):
    """Media evidence bound to one source version and thumbnail profile."""
    model_config = ConfigDict(extra="ignore")
    source_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    image_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    image_file: Annotated[str, Field(min_length=1, max_length=2000)]
    profile: Literal["atlas-thumbnail-1"]
    codec: Literal["png"]
    width: Literal[128, 256, 512]
    height: Literal[128, 256, 512]
    pixel_min: Annotated[StrictInt, Field(ge=0, le=255)]
    pixel_max: Annotated[StrictInt, Field(ge=0, le=255)]
    spatial_range: Annotated[StrictInt, Field(ge=9, le=255)]

    @model_validator(mode="after")
    def square_and_visible(self) -> Self:
        if self.width != self.height or self.pixel_max - self.pixel_min <= 8:
            raise ValueError("Thumbnail must be square with visible pixel variation")
        return self
