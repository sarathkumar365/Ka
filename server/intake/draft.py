"""What the extraction model may propose. Anything not listed here cannot reach the data repo."""

import re
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class _Draft(BaseModel):
    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def _nulls_mean_missing(cls, data):
        """Models often answer null for an empty string field; treat that as not given."""
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if v is not None}
        return data


def _text(v):
    """The model sometimes sends numbers where text belongs; read them as text."""
    return None if v is None else str(v).strip()


def _date(v, month: str) -> str | None:
    """Year-only dates need a month; present/current mean no end date."""
    v = _text(v)
    if not v or v.lower() in {"present", "current", "now", "today", "ongoing"}:
        return None
    if re.fullmatch(r"\d{4}", v):
        return f"{v}-{month}"
    return v


def _start(v):
    return _date(v, "01")


def _end(v):
    return _date(v, "12")


def _strip_nulls(items):
    return [
        {k: v for k, v in i.items() if v is not None} if isinstance(i, dict) else i for i in items
    ]


class DraftNumber(_Draft):
    value: Decimal
    unit: str = ""
    label: str = ""


class DraftHighlight(_Draft):
    text: str
    tech: list[str] = []
    domains: list[str] = []  # domain NAMES; resolved to ids when a card is approved
    numbers: list[DraftNumber] = []


class DraftJob(_Draft):
    company: str
    position: str
    employment_type: Literal["full_time", "part_time", "contract"] | None = None
    location: str = ""
    start: str | None = None
    end: str | None = None
    summary: str = ""
    highlights: list[DraftHighlight] = []

    _start_date = field_validator("start", mode="before")(_start)
    _end_date = field_validator("end", mode="before")(_end)


class DraftEducation(_Draft):
    level: str
    institution: str
    program: str
    city: str = ""
    country: str = ""
    start: str | None = None
    end: str | None = None
    grade: str | None = None
    grade_scale: str | None = None

    _start_date = field_validator("start", mode="before")(_start)
    _end_date = field_validator("end", mode="before")(_end)


class DraftProfile(_Draft):
    name: str | None = None
    emails: list[str] = []
    phones: list[str] = []
    location: dict[str, str] | None = None
    links: list[dict[str, str]] = []
    languages: list[dict[str, str]] = []

    @field_validator("location", mode="before")
    @classmethod
    def _loc(cls, v):
        return {k: x for k, x in v.items() if x is not None} if isinstance(v, dict) else v

    _links = field_validator("links", "languages", mode="before")(_strip_nulls)


class ResumeDraft(_Draft):
    profile: DraftProfile = DraftProfile()
    education: list[DraftEducation] = []
    domains: list[str] = []
    jobs: list[DraftJob] = []
