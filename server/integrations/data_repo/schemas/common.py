from datetime import date
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field


class KaModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


def _check_partial_date(v: str) -> str:
    if len(v) == 10:
        date.fromisoformat(v)
    return v


PartialDate = Annotated[
    str,
    Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])(-\d{2})?$"),
    AfterValidator(_check_partial_date),
]


def require_unique(ids: list[str], what: str) -> None:
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"duplicate {what} ids: {sorted(dupes)}")
