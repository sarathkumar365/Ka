from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from server.integrations.data_repo.schemas.common import KaModel


class StatementSummary(KaModel):
    bank: Literal["scotiabank"]
    account_number: str
    period_start: date
    period_end: date
    opening_balance: Decimal
    total_withdrawals: Decimal
    total_deposits: Decimal
    closing_balance: Decimal


class RawRow(KaModel):
    row_number: int
    month: int
    day: int
    type_text: str
    description: str
    amount: Decimal  # unsigned, as printed
    column: Literal["withdrawn", "deposited"]
    balance: Decimal


class ParsedStatement(KaModel):
    summary: StatementSummary
    rows: list[RawRow]
    file_name: str


class LedgerRow(KaModel):
    row_number: int
    date: date
    type_text: str
    description: str
    amount: Decimal  # signed, negative is money out
    balance: Decimal


class CheckFailure(KaModel):
    check: Literal[
        "row_balance", "summary_totals", "opening_closing", "column_direction", "date_out_of_period"
    ]
    row_number: int | None
    message: str


class Transaction(KaModel):
    id: str
    account: str
    statement_id: str
    date: date
    type: str
    description: str
    amount: Decimal
    balance: Decimal
    tag: str
    category: str = ""
    linked_id: str = ""


class StatementRecord(KaModel):
    statement_id: str
    account: str
    period_start: date
    period_end: date
    opening_balance: Decimal
    total_withdrawals: Decimal
    total_deposits: Decimal
    closing_balance: Decimal
    file_name: str
    imported_at: datetime
