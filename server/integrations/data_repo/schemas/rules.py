from typing import Literal

from pydantic import Field, model_validator

from .common import KaModel, PartialDate, require_unique

Tag = Literal[
    "purchase", "refund", "nsf_return", "own_transfer", "borrowing", "debt_payment", "income", "fee"
]


class MerchantRule(KaModel):
    id: str = Field(pattern=r"^R-\d{3}$")
    match: str
    category: str
    approved: PartialDate


class MerchantRulesFile(KaModel):
    rules: list[MerchantRule] = []

    @model_validator(mode="after")
    def _unique(self):
        require_unique([r.id for r in self.rules], "merchant rule")
        return self


class TransactionTypeRule(KaModel):
    bank: str
    type_text: str
    tag: Tag
    nets_against_original: bool = False


class TransactionTypesFile(KaModel):
    types: list[TransactionTypeRule] = []
