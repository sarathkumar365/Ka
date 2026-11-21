"""Toolkit folders: manifest.yaml (name, one-line description, flag), tools.py, instructions.md."""

from functools import cache
from pathlib import Path

from pydantic import Field
from ruamel.yaml import YAML

from server.config import Config
from server.flags import is_on
from server.integrations.data_repo.schemas.common import KaModel

ROOT = Path(__file__).parent


class Manifest(KaModel):
    name: str = Field(pattern=r"^[a-z]+$")
    description: str = Field(max_length=120)
    flag: str | None = None
    private: bool = False  # loading it moves the chat to the private model chain


@cache
def manifests() -> dict[str, Manifest]:
    out = {}
    for path in sorted(ROOT.glob("*/manifest.yaml")):
        m = Manifest(**YAML(typ="safe").load(path.read_text()))
        if m.name != path.parent.name:
            raise ValueError(f"{path}: name must match its folder")
        out[m.name] = m
    return out


def enabled(cfg: Config, name: str) -> bool:
    m = manifests().get(name)
    return m is not None and (m.flag is None or is_on(cfg, m.flag))


def available(cfg: Config) -> list[Manifest]:
    """Toolkits the agent may load now (core is always on, so it is not listed)."""
    return [m for m in manifests().values() if m.name != "core" and enabled(cfg, m.name)]


def instructions(name: str) -> str:
    return (ROOT / name / "instructions.md").read_text().strip()


def visible_tools(cfg: Config, loaded: list[str]):
    """Tools the model sees: core plus loaded toolkits, minus anything whose flag is off."""
    from server.agent.tools.registry import REGISTRY

    kits = {"core", *(k for k in loaded if enabled(cfg, k))}
    return [
        t for t in REGISTRY.values()
        if t.toolkit in kits and (t.flag is None or is_on(cfg, t.flag))
    ]  # fmt: skip
