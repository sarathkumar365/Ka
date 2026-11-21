import logging
import os
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator
from ruamel.yaml import YAML, YAMLError

log = logging.getLogger(__name__)


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


class Price(BaseModel):
    """US dollars per million tokens, for models whose provider reports no cost."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    input_per_m: Decimal
    output_per_m: Decimal


class GoogleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    client_file: Path  # OAuth desktop client JSON; used in place, never copied
    # Per account: filled from users/<id>/settings.yaml by user_config; refused in config.yaml.
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
    prices: dict[str, Price] = {}  # model id -> price; lets the loop cost cap see every call
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
        """Shared by every account; read by the commit guard (scripts/commit_guard.py)."""
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
    google = raw.get("google") if isinstance(raw.get("google"), dict) else {}
    for key in ("drive_folder_id", "sheet_id"):
        if google.pop(key, None) is not None:  # each account sets its own in Settings
            log.warning("config.yaml google.%s is ignored: each account sets it in Settings", key)
    per_account = sorted({"user_id", "repo_root"} & set(raw))
    if per_account:  # set per request from the signed-in account, never in the file
        raise ConfigError(f"{chosen}: not allowed in config.yaml: {', '.join(per_account)}")
    try:
        return Config(**raw)
    except ValidationError as e:
        raise ConfigError(f"{chosen}: {e}") from e
