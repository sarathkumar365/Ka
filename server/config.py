import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator
from ruamel.yaml import YAML


class ConfigError(Exception):
    pass


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    data_repo: Path
    flags: dict[str, bool] = {}

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
    def denylist_path(self) -> Path:
        return self.data_repo / "local" / "denylist.txt"


def load_config(path: Path | None = None) -> Config:
    chosen = path or (Path(os.environ["KA_CONFIG"]) if "KA_CONFIG" in os.environ else Path("config.yaml"))
    if not chosen.is_file():
        raise ConfigError(f"config not found: {chosen}. Copy config.example.yaml to config.yaml")
    raw = YAML(typ="safe").load(chosen.read_text()) or {}
    try:
        return Config(**raw)
    except ValidationError as e:
        raise ConfigError(f"{chosen}: {e}") from e
