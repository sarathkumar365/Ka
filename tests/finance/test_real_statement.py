import os
from pathlib import Path

import pytest

from server.finance.parser import parse_statement
from server.finance.reconcile import reconcile

REAL = os.environ.get("KA_REAL_STATEMENT")


@pytest.mark.skipif(not REAL, reason="set KA_REAL_STATEMENT to a real statement PDF")
def test_real_statement_passes_all_checks():
    parsed = parse_statement(Path(REAL).expanduser())
    assert parsed.rows
    assert reconcile(parsed)[1] == []
