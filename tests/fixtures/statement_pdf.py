"""Builds fake Scotiabank-style chequing statement PDFs at the real column positions."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal

from reportlab.pdfgen import canvas

PAGE_H = 792
FONT, SIZE = "Helvetica", 9
X_DATE, X_TEXT, X_WITHDRAWN, X_DEPOSITED, X_BALANCE = 73, 113, 306, 371, 436


@dataclass
class SpecRow:
    date: date
    type_text: str
    description: str | None
    amount: Decimal  # signed, negative is money out
    column: Literal["withdrawn", "deposited"] | None = None  # None: derived from sign
    balance: Decimal | None = None  # None: computed


@dataclass
class StatementSpec:
    account_number: str = "111112222233"
    period_start: date = date(2031, 3, 24)
    period_end: date = date(2031, 4, 23)
    opening_balance: Decimal = Decimal("500.00")
    rows: list[SpecRow] = field(default_factory=list)
    rows_per_page: int = 20
    scotiabank: bool = True
    text_layer: bool = True
    totals: tuple[Decimal, Decimal] | None = None  # (withdrawals, deposits) override
    closing_balance: Decimal | None = None  # override


def _money(v: Decimal, dollar: bool = False) -> str:
    s = f"{v:,.2f}"
    return f"${s}" if dollar else s


def _long(d: date) -> str:
    return f"{d:%B} {d.day}, {d.year}"


def _short(d: date) -> str:
    return f"{d:%b} {d.day}"


def build_statement(path: Path, spec: StatementSpec) -> None:
    if not spec.text_layer:
        return _build_scanned(path)
    balances, running = [], spec.opening_balance
    for r in spec.rows:
        running = r.balance if r.balance is not None else running + r.amount
        balances.append(running)
    out = sum((-r.amount for r in spec.rows if r.amount < 0), Decimal(0))
    inn = sum((r.amount for r in spec.rows if r.amount > 0), Decimal(0))
    withdrawals, deposits = spec.totals or (out, inn)
    closing = spec.closing_balance if spec.closing_balance is not None else running

    pages = [
        spec.rows[i : i + spec.rows_per_page] for i in range(0, len(spec.rows), spec.rows_per_page)
    ]
    pages = pages or [[]]
    c = canvas.Canvas(str(path), pagesize=(612, 792))
    c.setFont(FONT, SIZE)

    def txt(x: float, top: float, s: str, right: bool = False) -> None:
        y = PAGE_H - top - SIZE
        (c.drawRightString if right else c.drawString)(x, y, s)

    idx = 0
    for n, page_rows in enumerate(pages, start=1):
        c.setFont(FONT, SIZE)
        last_page = n == len(pages)
        txt(500, 100, "000000144")
        txt(500, 300, "734730")
        if n == 1:
            txt(430, 75, "Your account number:")
            acct = spec.account_number
            txt(430, 85, f"{acct[:5]} {acct[5:10]} {acct[10:]}")
            if spec.scotiabank:
                txt(430, 135, "www.scotiabank.com")
            txt(73, 250, "Your Preferred Package account summary")
            txt(73, 266, f"Opening Balance on {_long(spec.period_start)}")
            txt(436, 266, _money(spec.opening_balance, True), right=True)
            txt(73, 280, "Minus total withdrawals")
            txt(436, 280, _money(withdrawals, True), right=True)
            txt(73, 294, "Plus total deposits")
            txt(436, 294, _money(deposits, True), right=True)
            txt(73, 308, f"Closing Balance on {_long(spec.period_end)}")
            txt(436, 308, _money(closing, True), right=True)
            txt(73, 360, "Here's what happened in your account this statement period")
            top = 383
        else:
            txt(73, 60, "MR TEST PERSON")
            txt(73, 70, "Your Preferred Package account")
            txt(
                73,
                80,
                f"{_short(spec.period_start)} to {_long(spec.period_end)} {spec.account_number}",
            )
            txt(73, 105, "Here's what happened in your account (continued)")
            top = 128
        txt(272, top, "Amounts")
        txt(337, top, "Amounts")
        txt(X_DATE, top + 9, "Date")
        txt(X_TEXT, top + 9, "Transactions")
        txt(252, top + 9, "withdrawn ($)")
        txt(322, top + 9, "deposited ($)")
        txt(395, top + 9, "Balance ($)")
        top += 26
        if n == 1:
            txt(X_DATE, top, _short(spec.period_start))
            txt(X_TEXT, top, "Opening Balance")
            txt(X_BALANCE, top, _money(spec.opening_balance), right=True)
            top += 18
        for r in page_rows:
            col = r.column or ("withdrawn" if r.amount < 0 else "deposited")
            txt(X_DATE, top, _short(r.date))
            txt(X_TEXT, top, r.type_text)
            txt(
                X_WITHDRAWN if col == "withdrawn" else X_DEPOSITED,
                top,
                _money(abs(r.amount)),
                right=True,
            )
            txt(
                X_BALANCE,
                top,
                _money(balances[idx]) if balances[idx] >= 0 else f"-{_money(-balances[idx])}",
                right=True,
            )
            idx += 1
            if r.description:
                txt(X_TEXT, top + 9, r.description)
                top += 27
            else:
                top += 18
        if last_page:
            txt(X_DATE, top, _short(spec.period_end))
            txt(X_TEXT, top, "Closing Balance")
            txt(X_BALANCE, top, _money(closing, True), right=True)
        else:
            txt(300, 735, "continued on next page")
        txt(300, 750, f"Page {n} of {len(pages)}")
        txt(500, 770, "6980130")
        c.showPage()
    c.save()


def _build_scanned(path: Path) -> None:
    """A page with a drawn box and no text, like a scan with no OCR layer."""
    c = canvas.Canvas(str(path), pagesize=(612, 792))
    c.rect(50, 50, 200, 200)
    c.showPage()
    c.save()
