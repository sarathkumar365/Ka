"""Where imported finance rows live. CSV now; a Google Sheet backend can implement the same interface."""

import csv
import os
from pathlib import Path
from typing import Protocol

from .models import StatementRecord, Transaction


class FinanceStore(Protocol):
    def statements(self) -> list[StatementRecord]: ...
    def transactions(self) -> list[Transaction]: ...
    def add_import(self, statement: StatementRecord, rows: list[Transaction]) -> int: ...


class CsvFinanceStore:
    def __init__(self, folder: Path) -> None:
        self.folder = folder
        folder.mkdir(parents=True, exist_ok=True)
        self._statements = folder / "statements.csv"
        self._transactions = folder / "transactions.csv"

    def _read(self, path: Path, model):
        if not path.is_file():
            return []
        with path.open(newline="", encoding="utf-8") as f:
            return [model(**row) for row in csv.DictReader(f)]

    def _write(self, path: Path, model, items) -> None:
        tmp = path.with_suffix(".tmp")
        with tmp.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(model.model_fields))
            w.writeheader()
            for item in items:
                w.writerow({k: str(v) for k, v in item.model_dump().items()})
        os.replace(tmp, path)

    def statements(self) -> list[StatementRecord]:
        return self._read(self._statements, StatementRecord)

    def transactions(self) -> list[Transaction]:
        return self._read(self._transactions, Transaction)

    def add_import(self, statement: StatementRecord, rows: list[Transaction]) -> int:
        # Transactions first: if we stop between the two writes, re-running finishes the import.
        stored_rows = self.transactions()
        known = {t.id for t in stored_rows}
        new = [r for r in rows if r.id not in known]
        if new:
            self._write(self._transactions, Transaction, stored_rows + new)
        stored = self.statements()
        if statement.statement_id not in {s.statement_id for s in stored}:
            self._write(self._statements, StatementRecord, stored + [statement])
        return len(new)
