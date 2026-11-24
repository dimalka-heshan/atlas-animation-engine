"""Audio-relative, continuous coarse mouth-cue timelines (not phonemes)."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CueValue = Literal['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'X']


class MouthCue(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    value: CueValue

    @model_validator(mode='after')
    def positive_interval(self):
        if self.end <= self.start:
            raise ValueError('Cue end must follow start')
        return self


class LipSyncTimeline(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    audio_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    duration_seconds: float = Field(gt=0, le=180)
    cues: list[MouthCue] = Field(min_length=1, max_length=10000)
    method: Literal['rhubarb'] = 'rhubarb'
    version: str = Field(min_length=1)
    transcript_sha256: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    executable_sha256: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')

    @model_validator(mode='after')
    def continuous_bounded(self):
        previous = 0.0
        for cue in self.cues:
            if abs(cue.start - previous) > 1e-8 or cue.end > self.duration_seconds + 1e-8:
                raise ValueError('Cues must be sorted, contiguous, nonoverlapping and within audio duration')
            previous = cue.end
        if abs(previous - self.duration_seconds) > 1e-8:
            raise ValueError('Cues must cover the measured audio duration; silence uses X')
        return self


class FacialControls(BaseModel):
    """Explicit bindings for a single actor's descendant mesh or armature."""
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    kind: Literal['shape_keys', 'jaw_bone']
    object: str = Field(min_length=1)
    mapping: dict[CueValue, str] = Field(default_factory=dict)
    bone: str | None = None
    axis: Literal['X', 'Y', 'Z'] = 'X'
    angles: dict[CueValue, float] = Field(default_factory=dict)

    @model_validator(mode='after')
    def complete_mapping(self):
        if self.kind == 'shape_keys':
            if set(self.mapping) != set('ABCDEFGH') or not all(self.mapping.values()):
                raise ValueError('Shape-key mapping must name all A-H controls; X resets them')
            if len(set(self.mapping.values())) != 8:
                raise ValueError('Each mouth cue must map to a distinct shape key')
        elif not self.bone or set(self.angles) != set('ABCDEFGHX') or self.angles['X'] != 0:
            raise ValueError('Jaw mapping requires a bone, angles for A-H/X, and X=0 radians')
        return self
