from dataclasses import dataclass
from typing import Literal, Protocol

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserError(Exception):
    """An actionable error suitable for the local UI."""


class BusyError(UserError):
    pass


class MingOptions(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    task: Literal["TTS", "EMOTION", "BASIC", "FREEFORM", "VOICE_DESIGN", "IP", "DIALECT"] = "TTS"
    language: Literal["en", "zh", "de", "es", "fr", "ko", "ja"] = "en"
    emotion: Literal["happy", "sad", "angry", "afraid", "disgusted", "surprised", "neutral"] = (
        "neutral"
    )
    speed: Literal["slow", "normal", "fast"] = "normal"
    pitch: Literal["low", "normal", "high"] = "normal"
    loudness: Literal["low", "normal", "high"] = "normal"
    instruction: str = Field(default="", max_length=1000)
    voice: Literal["US_Emma", "UK_George", "UK_Charlotte"] = "US_Emma"
    dialect: Literal["chuanyu dialect", "cantonese"] = "cantonese"


class GenerationSettings(BaseModel):
    """Persistent defaults for individual voices."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    ming: MingOptions = Field(default_factory=MingOptions)
    language: str = "auto"
    volume: float = Field(default=100.0, ge=0, le=300)
    speed: float = Field(default=1.0, ge=0.5, le=1.5)
    duration: float | None = Field(default=None, ge=0.5, le=120)
    steps: int = Field(default=32, ge=4, le=64)
    denoise: bool = True
    guidance_scale: float = Field(default=2.0, ge=0, le=4)
    preprocess_prompt: bool = True
    postprocess_output: bool = True

    @field_validator("language")
    @classmethod
    def valid_language(cls, value: str) -> str:
        if value not in {"pt", "en", "auto"}:
            raise ValueError("Idioma deve ser pt, en ou auto.")
        return value


class GenerationRequest(GenerationSettings):
    text: str = Field(min_length=1, max_length=2000)
    ref_text: str = Field(default="", max_length=4000)
    autoqueue_general: bool = False
    requester_name: str = Field(default="", max_length=80)
    requester_id: str = Field(default="", max_length=80)

    @field_validator("text", "ref_text", mode="before")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value


@dataclass
class Waveform:
    samples: np.ndarray
    sample_rate: int


class Engine(Protocol):
    def synthesize(self, reference: str, request: GenerationRequest) -> Waveform: ...
