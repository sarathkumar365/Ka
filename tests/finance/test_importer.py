import shutil
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from server.cli import main
from server.finance.importer import ImportFailed, commit_import, prepare_import
from server.finance.store import CsvFinanceStore
from server.integrations.data_repo.loader import load_data
from tests.fixtures.statement_pdf import SpecRow, StatementSpec, build_statement

FIX = Path(__file__).parents[1] / "fixtures" / "data"


def replace_accounts(data, accounts):
    return replace(data, accounts=data.accounts.model_copy(update={"accounts": accounts}))


ROWS = [
    SpecRow(date(2031, 3, 25), "Point of sale purchase", "Apos Corner Cafe", Decimal("-4.50")),
    SpecRow(date(2031, 3, 26), "Payroll dep.", "Example Co Ltd.", Decimal("1250.00")),
]


def test_prepare_commit_and_duplicate_guard(tmp_path):
    pdf = tmp_path / "s.pdf"
    build_statement(pdf, StatementSpec(rows=ROWS))
    data, store = load_data(FIX), CsvFinanceStore(tmp_path / "fin")
    p = prepare_import(pdf, data, store)
    assert p.statement.statement_id == "scotiabank-chequing-2233-2031-04"
    assert p.failures == [] and len(p.transactions) == 2
    assert commit_import(p, store) == 2
    assert prepare_import(pdf, data, store).already_imported
    with pytest.raises(ImportFailed, match="already imported"):
        commit_import(prepare_import(pdf, data, store), store)


def test_failed_checks_write_nothing_and_unknown_account_is_explained(tmp_path):
    bad = tmp_path / "bad.pdf"
    build_statement(bad, StatementSpec(rows=ROWS, closing_balance=Decimal("1.00")))
    data, store = load_data(FIX), CsvFinanceStore(tmp_path / "fin")
    p = prepare_import(bad, data, store)
    assert [f.check for f in p.failures] == ["opening_closing"]
    with pytest.raises(ImportFailed):
        commit_import(p, store)
    assert store.transactions() == []
    other = tmp_path / "other.pdf"
    build_statement(other, StatementSpec(account_number="999988887777", rows=ROWS))
    with pytest.raises(ImportFailed, match="7777 is not in accounts.yaml"):
        prepare_import(other, data, store)
    # full number beats a last4 collision, wherever the colliding account sits in the file
    clash = data.accounts.accounts[2].model_copy(
        update={"id": "A-09", "last4": "2233", "match": []}
    )
    shuffled = replace_accounts(data, [clash, *data.accounts.accounts])
    assert prepare_import(bad, shuffled, store).statement.account == "A-01"


def test_cli_import_prompt_and_statements_list(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "base" / "users" / "avery"
    shutil.copytree(FIX, repo)
    (repo / "local" / "statements").mkdir(parents=True)
    pdf = repo / "local" / "statements" / "s.pdf"
    build_statement(pdf, StatementSpec(rows=ROWS))
    cfg = tmp_path / "c.yaml"
    cfg.write_text(f"data_repo: {tmp_path / 'base'}\n")
    monkeypatch.setenv("KA_CONFIG", str(cfg))

    monkeypatch.setattr("builtins.input", lambda _: "n")
    assert main(["--user", "avery", "import", str(pdf)]) == 0
    assert "declined" in capsys.readouterr().out
    assert main(["--user", "avery", "statements"]) == 0 and capsys.readouterr().out.startswith("new")

    monkeypatch.setattr("builtins.input", lambda _: "y")
    assert main(["--user", "avery", "import", str(pdf)]) == 0
    assert "checks: 4 passed" in capsys.readouterr().out
    assert main(["--user", "avery", "statements"]) == 0 and capsys.readouterr().out.startswith("imported")

    scanned = tmp_path / "scan.pdf"
    build_statement(scanned, StatementSpec(text_layer=False))
    assert main(["--user", "avery", "import", str(scanned)]) == 1
    assert "no text layer" in capsys.readouterr().out
