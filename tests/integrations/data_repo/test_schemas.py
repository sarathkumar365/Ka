from decimal import Decimal

import pytest
from pydantic import ValidationError

from server.integrations.data_repo.schemas.accounts import Account
from server.integrations.data_repo.schemas.ids import IdsFile
from server.integrations.data_repo.schemas.jobs import Highlight, Number
from server.integrations.data_repo.schemas.profile import Address, Profile


def test_rejects_bad_ids_dates_enums_and_extra_fields():
    with pytest.raises(ValidationError):
        Highlight(id="H-1", text="x")
    with pytest.raises(ValidationError):
        Account(id="A-01", kind="cash", label="x")
    with pytest.raises(ValidationError):
        Account(id="A-01", kind="chequing", label="x", bogus=1)
    with pytest.raises(ValidationError):
        Address(address="x", **{"from": "2024-13"})
    with pytest.raises(ValidationError):
        IdsFile(next={"H": 0})


def test_accepts_from_key_and_keeps_decimals_exact():
    a = Address(address="1 Test St", **{"from": "2024-01"}, current=True)
    assert a.from_ == "2024-01"
    assert Number(value="1.50", unit="%", label="x").value == Decimal("1.50")
    with pytest.raises(ValidationError):
        Profile(
            name="A",
            addresses=[
                Address(address="a", **{"from": "2020-01"}, current=True),
                Address(address="b", **{"from": "2021-01"}, current=True),
            ],
        )
