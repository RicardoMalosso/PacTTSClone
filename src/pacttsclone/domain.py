from dataclasses import dataclass
from typing import Protocol

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserError(Exception):
    """An actionable error suitable for the local UI."""


class BusyError(UserError):
    pass


class GenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    text: str = Field(min_length=1, max_length=2000)
    ref_text: str = Field(default="", max_length=4000)
    language: str = "pt"
    speed: float = Field(default=1.0, ge=0.5, le=1.5)
    steps: int = Field(default=32, ge=4, le=64)

    @field_validator("text", "ref_text", mode="before")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value

    @field_validator("language")
    @classmethod
    def valid_language(cls, value: str) -> str:
        if value not in {"pt", "en", "auto"}:
            raise ValueError("Idioma deve ser pt, en ou auto.")
        return value


@dataclass
class Waveform:
    samples: np.ndarray
    sample_rate: int


class Engine(Protocol):
    def synthesize(self, reference: str, request: GenerationRequest) -> Waveform: ...
