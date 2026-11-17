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

    @model_validator(mode="after")
    def _zdr_needs_openrouter(self):
        if (self.zdr or self.only) and self.provider != "openrouter":
            raise ValueError("zdr and only are OpenRouter options; use provider openrouter")
        return self


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    data_repo: Path
    flags: dict[str, bool] = {}
    models: dict[str, ModelConfig] = {}
    private_models: list[ModelConfig] = []  # tried in order for finance conversations
    ui_hosts: list[str] = []

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

    @property
    def statements_dir(self) -> Path:
        return self.data_repo / "local" / "statements"

    @property
    def finance_dir(self) -> Path:
        return self.data_repo / "local" / "finance"

    @property
    def db_path(self) -> Path:
        return self.data_repo / "local" / "ka.db"

    @property
    def denylist_path(self) -> Path:
        return self.data_repo / "local" / "denylist.txt"


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
