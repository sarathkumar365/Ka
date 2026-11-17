from typing import Literal

from pydantic import Field, model_validator

from .common import KaModel, require_unique


class Guardrail(KaModel):
    id: str = Field(pattern=r"^G-\d{2}$")
    text: str
    kind: Literal["never_claim", "limit"]
    scope: Literal["all", "resume", "cover_letter"] = "all"
    reason: str | None = None


class GuardrailsFile(KaModel):
    rules: list[Guardrail] = []

    @model_validator(mode="after")
    def _unique(self):
        require_unique([r.id for r in self.rules], "guardrail")
        return self
