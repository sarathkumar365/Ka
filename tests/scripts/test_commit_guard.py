from scripts.commit_guard import find_violations


def rules(files, denylist=()):
    return [v.rule for v in find_violations(files, list(denylist))]


def test_blocks_env_pdf_and_secret_but_allows_examples_and_fixtures():
    assert rules({".env": b"X=1"}) == ["env_file"]
    assert rules({".env.example": b"X="}) == []
    assert rules({"docs/a.PDF": b"%PDF"}) == ["pdf"]
    assert rules({"tests/fixtures/a.pdf": b"%PDF"}) == []
    assert rules({"a.py": b'K = "sk-' + b"a" * 24 + b'"'}) == ["secret"]


def test_denylist_ignores_case_and_spaces_and_never_echoes_the_entry():
    v = find_violations({"a.md": b"acct 12345 67890 12"}, ["123456789012"])
    assert [x.rule for x in v] == ["denylist"]
    assert "123456789012" not in v[0].detail
    assert rules({"a.md": b"on"}, ["on"]) == []
    assert rules({"a.bin": b"\xff\xfe\x00"}, ["zzzz"]) == []
