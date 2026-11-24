"""Validated persistent voice profile and reference permission contracts."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator

from engine.voice.provider import MODEL_REVISION, SOURCE_REVISION

Text = Annotated[str, Field(min_length=1, max_length=20000)]


class VoiceConsent(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    approved: StrictBool
    owner: Text
    allowed_usage: Text
    evidence: Text


class VoiceReference(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    path: Text
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    duration_seconds: float = Field(gt=5, le=30)
    sample_rate: StrictInt = Field(ge=8000, le=192000)
    channels: Literal[1, 2]
    sample_width: Literal[2]
    frames: StrictInt = Field(gt=0)
    peak: float = Field(gt=0, le=1)
    clipped_samples: StrictInt = Field(ge=0)


class VoiceProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    schema_version: Literal[1]
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    name: str = Field(min_length=1, max_length=200)
    provider: Literal["chatterbox-turbo"]
    source_revision: str
    model_revision: str
    language: Literal["en"]
    settings: dict
    tags: list[Annotated[str, Field(max_length=100)]] = Field(max_length=100)
    created_at: Text
    consent: VoiceConsent | None
    voice_kind: Literal["approved-reference", "model-bundled-conditioning"]
    reference: VoiceReference | None

    @model_validator(mode="after")
    def pinned_and_approved(self):
        if self.source_revision != SOURCE_REVISION or self.model_revision != MODEL_REVISION:
            raise ValueError("Voice profile runtime/model pin mismatch")
        if self.voice_kind == "approved-reference":
            if self.reference is None or self.consent is None or not self.consent.approved:
                raise ValueError("Reference voice requires pinned reference and approved consent")
        elif self.reference is not None:
            raise ValueError("Bundled conditioning cannot contain a user reference")
        return self
