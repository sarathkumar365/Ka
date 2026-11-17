from typing import Literal

from pydantic import Field, model_validator

from .common import KaModel, require_unique


class Account(KaModel):
    id: str = Field(pattern=r"^A-\d{2}$")
    bank: str = ""
    kind: Literal["chequing", "savings", "credit", "loan", "investment"]
    label: str
    last4: str | None = None
    mine: bool = True
    primary: bool = False
    match: list[str] = []


class AccountsFile(KaModel):
    accounts: list[Account] = []

    @model_validator(mode="after")
    def _checks(self):
        require_unique([a.id for a in self.accounts], "account")
        if sum(a.primary for a in self.accounts) > 1:
            raise ValueError("at most one primary account")
        return self
