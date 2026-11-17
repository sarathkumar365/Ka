# Conventions

- Python 3.13, uv, ruff (line length 100), pytest.
- Type hints on public functions. Pydantic models use `extra="forbid"`.
- Money: `Decimal`; compare and store with two decimals.
- Tests mirror `server/` under `tests/`. Names are `test_<behaviour>`. Few tests, aimed at risk.
- Synthetic fixtures only; invented people, merchants, amounts.
- Commits: one logical change, prefix `feat|fix|refactor|test|docs|chore`.
