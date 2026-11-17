from typing import Literal

from pydantic import Field, model_validator

from .common import KaModel, PartialDate, require_unique


class MemoryEntry(KaModel):
    id: str = Field(pattern=r"^M-\d{4}$")
    type: Literal["fact", "preference", "rule"]
    text: str
    source: str | None = None
    created: PartialDate
    updated: PartialDate
    status: Literal["active", "retired"] = "active"
    replaced_by: str | None = None


class MemoryFile(KaModel):
    entries: list[MemoryEntry] = []

    @model_validator(mode="after")
    def _unique(self):
        require_unique([e.id for e in self.entries], "memory")
        return self
