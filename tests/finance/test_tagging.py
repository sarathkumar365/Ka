from datetime import date
from decimal import Decimal
from pathlib import Path

from server.finance.models import LedgerRow
from server.finance.tagging import tag_rows
from server.integrations.data_repo.loader import load_data

DATA = load_data(Path(__file__).parents[1] / "fixtures" / "data")
SID = "scotiabank-chequing-2233-2031-04"


def L(n, day, type_text, desc, amount):
    return LedgerRow(
        row_number=n,
        date=date(2031, 4, day),
        type_text=type_text,
        description=desc,
        amount=Decimal(amount),
        balance=Decimal(0),
    )


def tag(rows, existing=()):
    return tag_rows(rows, SID, "A-01", DATA, list(existing))


def test_account_rules_decide_transfers_loans_and_returned_payments():
    r = tag(
        [
            L(1, 1, "MB-Transfer to", "9990001", "-50.00"),  # own savings
            L(2, 1, "MB-Transfer to", "5550009", "-50.00"),  # not mine: spending
            L(3, 2, "MB-Bill payment", "Example Lender", "-100.00"),
            L(4, 3, "Loans", "Example Lender EFT", "500.00"),
            L(5, 4, "Returned NSF cheque", "Example Lender", "100.00"),  # not new borrowing
            L(6, 5, "Deposit", "Example Lender", "10.00"),  # plain money in is a refund
        ]
    )
    assert [t.tag for t in r.transactions] == [
        "own_transfer",
        "purchase",
        "debt_payment",
        "borrowing",
        "nsf_return",
        "refund",
    ]
    assert r.transactions[4].linked_id == r.transactions[2].id
    assert r.transactions[0].id == f"{SID}-001"


def test_corrections_link_one_way_to_latest_unlinked_charge_and_unknowns_are_reported():
    r = tag(
        [
            L(1, 1, "Point of sale purchase", "Apos Corner Cafe", "-4.50"),
            L(2, 2, "Point of sale purchase", "Apos Corner Cafe", "-4.50"),
            L(3, 3, "Error correction", "Apos Corner Cafe", "4.50"),
            L(4, 4, "Error correction", "Apos Corner Cafe", "4.50"),
            L(5, 5, "Error correction", "Apos Corner Cafe", "4.50"),  # nothing left to undo
            L(6, 6, "Canada Example Benefit", "Government", "80.00"),
            L(7, 7, "Point of sale purchase", "Apos Mystery Shop", "-9.00"),
        ]
    )
    t = r.transactions
    assert (t[2].linked_id, t[3].linked_id, t[4].linked_id) == (t[1].id, t[0].id, "")
    assert t[0].linked_id == "" and t[1].linked_id == ""
    assert r.unlinked == [t[4].id]
    assert (t[0].category, t[5].tag, t[5].category) == ("dining", "income", "")
    assert r.unknown_types == ["Canada Example Benefit"]
    assert r.unknown_merchants == ["Apos Mystery Shop"]
