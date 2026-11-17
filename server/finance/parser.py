"""Scotiabank chequing statement PDF to rows. Word positions, no LLM."""

import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pdfplumber

from .models import ParsedStatement, RawRow, StatementSummary

# Column x ranges, measured on a real statement (US Letter, pdfplumber coordinates).
DATE_X = (70, 110)
WITHDRAWN_X1 = (250, 315)
DEPOSITED_X1 = (315, 380)
BALANCE_X1 = (380, 445)
MAX_X0 = 450  # barcodes and page numbers sit to the right of the table
TABLE_FONT_SIZES = (8, 9)  # header is 8 pt, rows 9 pt; barcode digits use other sizes

MONEY = re.compile(r"^-?\$?[\d,]+\.\d{2}$")
MONTHS = {
    m: i
    for i, m in enumerate(
        ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1
    )
}


class StatementFormatError(Exception):
    pass


def _money(text: str) -> Decimal:
    return Decimal(text.replace("$", "").replace(",", ""))


def _lines(page) -> list[list[dict]]:
    table_chars = page.filter(
        lambda o: (
            o["object_type"] != "char" or any(abs(o["size"] - z) < 0.1 for z in TABLE_FONT_SIZES)
        )
    )
    words = sorted(table_chars.extract_words(x_tolerance=1.5), key=lambda w: (w["top"], w["x0"]))
    lines: list[list[dict]] = []
    for w in words:
        if lines and abs(lines[-1][0]["top"] - w["top"]) <= 2:
            lines[-1].append(w)
        else:
            lines.append([w])
    return [sorted(line, key=lambda w: w["x0"]) for line in lines]


def _text(line: list[dict]) -> str:
    return " ".join(w["text"] for w in line)


def _parse_summary(first_page_text: str) -> StatementSummary:
    def find(pattern: str, what: str) -> re.Match:
        m = re.search(pattern, first_page_text)
        if not m:
            raise StatementFormatError(f"summary field not found: {what}")
        return m

    date_re = r"([A-Z][a-z]+) (\d{1,2}), (\d{4})"
    opening = find(rf"Opening Balance on {date_re} \$([\d,]+\.\d{{2}})", "opening balance")
    closing = find(rf"Closing Balance on {date_re} \$(-?[\d,]+\.\d{{2}})", "closing balance")
    withdrawals = find(r"Minus total withdrawals \$([\d,]+\.\d{2})", "total withdrawals")
    deposits = find(r"Plus total deposits \$([\d,]+\.\d{2})", "total deposits")
    account = find(r"\b(\d{5}) (\d{5}) (\d{2})\b", "account number")

    def to_date(m: re.Match):
        return datetime.strptime(f"{m[1]} {m[2]} {m[3]}", "%B %d %Y").date()

    return StatementSummary(
        bank="scotiabank",
        account_number=account[1] + account[2] + account[3],
        period_start=to_date(opening),
        period_end=to_date(closing),
        opening_balance=_money(opening[4]),
        total_withdrawals=_money(withdrawals[1]),
        total_deposits=_money(deposits[1]),
        closing_balance=_money(closing[4]),
    )


def parse_statement(path: Path) -> ParsedStatement:
    with pdfplumber.open(path) as pdf:
        if not any(p.chars for p in pdf.pages):
            raise StatementFormatError("no text layer: scanned statements are not supported")
        first_text = pdf.pages[0].extract_text(x_tolerance=1.5) or ""
        low = first_text.lower()
        if "scotiabank.com" not in low or "what happened in your account" not in low:
            raise StatementFormatError("not a Scotiabank chequing statement")
        summary = _parse_summary(first_text)

        rows: list[RawRow] = []
        for page_no, page in enumerate(pdf.pages, start=1):
            in_table = False
            for line in _lines(page):
                text = _text(line)
                if not in_table:
                    in_table = text.startswith("Date Transactions")
                    continue
                if text.startswith(("continued on next page", "Page ")):
                    break
                line = [w for w in line if w["x0"] < MAX_X0]
                if not line:
                    continue
                date_words = [w for w in line if DATE_X[0] <= w["x0"] < DATE_X[1]]
                if not date_words:
                    if rows:  # description line of the previous row, possibly on the prior page
                        extra = _text(line)
                        rows[-1].description = f"{rows[-1].description} {extra}".strip()
                    continue
                if len(date_words) != 2 or date_words[0]["text"] not in MONTHS:
                    raise StatementFormatError(f"page {page_no}: unreadable date in '{text}'")
                rest = [w for w in line if w not in date_words]
                money = [w for w in rest if MONEY.match(w["text"]) and w["x1"] > WITHDRAWN_X1[0]]
                type_text = " ".join(w["text"] for w in rest if w not in money)
                if type_text == "Opening Balance":
                    continue
                if type_text == "Closing Balance":
                    break
                amounts = [w for w in money if w["x1"] <= DEPOSITED_X1[1]]
                balances = [w for w in money if BALANCE_X1[0] < w["x1"] <= BALANCE_X1[1]]
                if len(amounts) != 1 or len(balances) != 1:
                    raise StatementFormatError(f"page {page_no}: cannot read amounts in '{text}'")
                column = "withdrawn" if amounts[0]["x1"] <= WITHDRAWN_X1[1] else "deposited"
                rows.append(
                    RawRow(
                        row_number=len(rows) + 1,
                        month=MONTHS[date_words[0]["text"]],
                        day=int(date_words[1]["text"]),
                        type_text=type_text,
                        description="",
                        amount=_money(amounts[0]["text"]),
                        column=column,
                        balance=_money(balances[0]["text"]),
                    )
                )
    return ParsedStatement(summary=summary, rows=rows, file_name=path.name)
