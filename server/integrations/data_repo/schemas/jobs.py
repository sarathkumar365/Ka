from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from .common import KaModel, PartialDate, require_unique


class Domain(KaModel):
    id: str = Field(pattern=r"^D-\d{2}$")
    name: str
    description: str


class Number(KaModel):
    value: Decimal
    unit: str
    label: str


class Highlight(KaModel):
    id: str = Field(pattern=r"^H-\d{3}$")
    text: str
    tech: list[str] = []
    domains: list[str] = []
    numbers: list[Number] = []
    retired: bool = False


class Job(KaModel):
    company: str
    position: str
    employment_type: Literal["full_time", "part_time", "contract"]
    location: str = ""
    start: PartialDate
    end: PartialDate | None = None
    summary: str = ""
    highlights: list[Highlight] = []


class JobsFile(KaModel):
    domains: list[Domain] = []
    jobs: list[Job] = []

    @model_validator(mode="after")
    def _unique(self):
        require_unique([d.id for d in self.domains], "domain")
        require_unique([h.id for j in self.jobs for h in j.highlights], "highlight")
        require_unique([f"{j.company}|{j.start}" for j in self.jobs], "job (company+start)")
        return self
