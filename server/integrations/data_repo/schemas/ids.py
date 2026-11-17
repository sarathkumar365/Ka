from typing import Annotated, Literal

from pydantic import Field

from .common import KaModel


class IdsFile(KaModel):
    next: dict[Literal["E", "D", "H", "G", "M", "A", "R", "O"], Annotated[int, Field(ge=1)]]
