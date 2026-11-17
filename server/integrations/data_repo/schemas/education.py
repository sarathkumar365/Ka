from typing import Literal

from pydantic import model_validator

from .common import KaModel, PartialDate, require_unique


class EducationEntry(KaModel):
    id: str
    level: Literal[
        "primary", "secondary", "bachelor", "master", "postgrad_certificate", "certification"
    ]
    institution: str
    program: str
    city: str = ""
    country: str = ""
    start: PartialDate | None = None
    end: PartialDate | None = None
    grade: str | None = None
    grade_scale: str | None = None
    issuer: str | None = None
    expiry: PartialDate | None = None

    @model_validator(mode="after")
    def _id_shape(self):
        import re

        if not re.fullmatch(r"E-\d{2}", self.id):
            raise ValueError(f"bad education id {self.id}")
        return self


class EducationFile(KaModel):
    entries: list[EducationEntry] = []

    @model_validator(mode="after")
    def _unique(self):
        require_unique([e.id for e in self.entries], "education")
        return self
