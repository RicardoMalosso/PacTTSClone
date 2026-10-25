import re

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    device: str = "auto"
    cpu_threads: int = Field(default=4, ge=1, le=128)
    keep_model_loaded: bool = True
    hotkey: str = "Ctrl+Alt+F9"
    max_queue: int = Field(default=30, ge=1, le=100)

    @field_validator("device")
    @classmethod
    def device_valid(cls, v):
        if v not in {"auto", "cpu", "cuda"}:
            raise ValueError("Choose Automatic, NVIDIA GPU or CPU.")
        return v

    @field_validator("hotkey")
    @classmethod
    def hotkey_valid(cls, v):
        from .hotkey import parse_hotkey

        if v:
            parse_hotkey(v)
        return v


def channel_name(value: str) -> str:
    value = value.strip().lower().removeprefix("#")
    if not re.fullmatch(r"[a-z0-9_]{1,25}", value) or value in {"api", "static"}:
        raise ValueError("Use a Twitch channel login, not its URL or display name.")
    return value


class EventRule(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    kind: str
    voice_id: str = Field(min_length=1, max_length=100)
    reward_id: str = Field(default="", max_length=100)
    min_bits: int = Field(default=1, ge=1, le=10000000)
    template: str = Field(default="{text}", min_length=1, max_length=1000)

    @field_validator("kind")
    @classmethod
    def kind_valid(cls, value):
        if value not in {
            "reward",
            "bits",
            "subscribe",
            "gift",
            "resub",
            "subscription_end",
            "follow",
            "raid",
            "online",
            "offline",
        }:
            raise ValueError("Unknown Twitch event type.")
        return value

    @field_validator("template")
    @classmethod
    def template_valid(cls, value):
        import string

        try:
            for _, field, spec, conversion in string.Formatter().parse(value):
                if field is not None and (
                    field
                    not in {
                        "text",
                        "username",
                        "bits",
                        "total",
                        "tier",
                        "months",
                        "viewers",
                        "reward",
                    }
                    or spec
                    or conversion
                ):
                    raise ValueError("Use only the documented event placeholders.")
        except ValueError as exc:
            raise ValueError("Invalid event text template.") from exc
        return value


class ChannelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    name: str
    enabled: bool = False
    transport: str = "irc"
    event_rules: list[EventRule] = Field(default_factory=list, max_length=50)
    paused: bool = False
    commands: dict[str, str] = Field(default_factory=dict)
    filter_level: str = "slurs"
    custom_filters: list[str] = Field(default_factory=list, max_length=200)
    delay_seconds: float = Field(default=5, ge=0, le=120)
    user_cooldown_seconds: float = Field(default=15, ge=0, le=600)
    max_message_chars: int = Field(default=300, ge=1, le=2000)

    @field_validator("transport")
    @classmethod
    def transport_valid(cls, value):
        if value not in {"irc", "oauth"}:
            raise ValueError("Choose IRC or OAuth.")
        return value

    @field_validator("event_rules")
    @classmethod
    def unique_rules(cls, values):
        keys = [(v.kind, v.reward_id if v.kind == "reward" else "") for v in values]
        if len(keys) != len(set(keys)):
            raise ValueError("Use one rule per event type or reward ID.")
        if any(v.kind == "reward" and not v.reward_id for v in values):
            raise ValueError("Choose a reward ID for each reward rule.")
        return values

    @field_validator("name")
    @classmethod
    def name_valid(cls, value):
        return channel_name(value)

    @field_validator("commands")
    @classmethod
    def commands_valid(cls, values):
        if len(values) > 50:
            raise ValueError("Maximum 50 commands per channel.")
        result = {}
        for key, voice in values.items():
            key = key.strip().casefold()
            if not re.fullmatch(r"![a-z0-9_]{1,30}", key) or not voice:
                raise ValueError("Commands must look like !lula and select a saved voice.")
            result[key] = voice
        return result

    @field_validator("filter_level")
    @classmethod
    def filter_valid(cls, value):
        if value not in {"slurs", "profanity", "strict"}:
            raise ValueError("Unknown filter level.")
        return value

    @field_validator("custom_filters")
    @classmethod
    def filters_valid(cls, values):
        result = []
        for term in values:
            term = term.strip()
            if not term or len(term) > 100:
                raise ValueError("Each custom term must contain 1–100 characters.")
            result.append(term)
        return result
