import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator
from ruamel.yaml import YAML, YAMLError


class ConfigError(Exception):
    pass


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Literal["openai", "openrouter", "ollama"]
    model: str
    base_url: str | None = None
    zdr: bool = False  # OpenRouter only: route to zero-data-retention providers
    only: list[str] = []  # OpenRouter only: allowed provider slugs, e.g. ["amazon-bedrock"]
    fallbacks: list[str] = []  # OpenRouter only: backup model ids, tried in order
    cache: bool = False  # mark the system prompt for prompt caching (Anthropic via OpenRouter)
    reasoning: Literal["low", "medium", "high"] | None = None  # thinking effort, when supported

    @model_validator(mode="after")
    def _zdr_needs_openrouter(self):
        routed = self.zdr or self.only or self.fallbacks or self.cache or self.reasoning
        if routed and self.provider != "openrouter":
            raise ValueError("zdr, only, fallbacks, cache and reasoning are OpenRouter options")
        return self


class GoogleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    client_file: Path  # OAuth desktop client JSON; used in place, never copied
    # Personal: read from users/<id>/settings.yaml. Still accepted here so an older config loads;
    # account setup copies them into the user's settings.
    drive_folder_id: str | None = None
    sheet_id: str | None = None

    @field_validator("client_file")
    @classmethod
    def _expand(cls, v: Path) -> Path:
        return v.expanduser()


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    data_repo: Path
    flags: dict[str, bool] = {}
    models: dict[str, ModelConfig] = {}
    private_models: list[ModelConfig] = []  # tried in order for finance conversations
    google: GoogleConfig | None = None
    ui_hosts: list[str] = []
    # Set by server.users.user_config: data_repo then points at users/<user_id> and repo_root at
    # the shared data repo, which holds the database and the denylist.
    user_id: str = ""
    repo_root: Path | None = None

    @field_validator("flags")
    @classmethod
    def _known_flags(cls, v: dict[str, bool]) -> dict[str, bool]:
        from server.flags import FLAGS

        unknown = sorted(set(v) - set(FLAGS))
        if unknown:
            raise ValueError(f"unknown flags: {', '.join(unknown)}")
        return v

    @field_validator("private_models")
    @classmethod
    def _private_keeps_no_data(cls, v: list[ModelConfig]) -> list[ModelConfig]:
        for m in v:
            if m.provider == "openai" or (m.provider == "openrouter" and not m.zdr):
                raise ValueError("private_models: use ollama, or openrouter with zdr: true")
        return v

    @field_validator("data_repo")
    @classmethod
    def _expand(cls, v: Path) -> Path:
        return v.expanduser()

    def model_for(self, task: Literal["chat", "small", "grader"]) -> ModelConfig:
        """Cheapest model that passes its evals, by task: chat (default), small, grader."""
        key = "default" if task == "chat" else task
        if key in self.models:
            return self.models[key]
        if "default" not in self.models:
            raise ConfigError("no models.default in config.yaml")
        return self.models["default"]

    @property
    def statements_dir(self) -> Path:
        return self.data_repo / "local" / "statements"

    @property
    def finance_dir(self) -> Path:
        return self.data_repo / "local" / "finance"

    @property
    def db_path(self) -> Path:
        return (self.repo_root or self.data_repo) / "local" / "ka.db"

    @property
    def google_dir(self) -> Path:
        return self.data_repo / "local" / "google"

    @property
    def denylist_path(self) -> Path:
        return (self.repo_root or self.data_repo) / "local" / "denylist.txt"

    @property
    def intake_dir(self) -> Path:
        return self.data_repo / "local" / "intake"


def load_config(path: Path | None = None) -> Config:
    chosen = path or (
        Path(os.environ["KA_CONFIG"]) if "KA_CONFIG" in os.environ else Path("config.yaml")
    )
    if not chosen.is_file():
        raise ConfigError(f"config not found: {chosen}. Copy config.example.yaml to config.yaml")
    try:
        raw = YAML(typ="safe").load(chosen.read_text()) or {}
    except YAMLError as e:
        raise ConfigError(f"{chosen}: invalid YAML") from e
    try:
        return Config(**raw)
    except ValidationError as e:
        raise ConfigError(f"{chosen}: {e}") from e
