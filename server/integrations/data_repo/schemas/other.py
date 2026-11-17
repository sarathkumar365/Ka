from typing import Any

from pydantic import Field, model_validator

from .common import KaModel, require_unique


class OtherRecord(KaModel):
    id: str = Field(pattern=r"^O-\d{3}$")
    type: str
    name: str
    details: dict[str, Any] = {}


class OtherFile(KaModel):
    types: list[str] = []
    records: list[OtherRecord] = []

    @model_validator(mode="after")
    def _checks(self):
        require_unique([r.id for r in self.records], "other record")
        bad = [r.id for r in self.records if r.type not in self.types]
        if bad:
            raise ValueError(f"records with unapproved type: {bad}")
        return self
