"""Live eval results: one JSONL file per run date, and a diff that lists new failures.

uv run python -m tests.evals.compare            # newest two files in tests/evals/results/
"""

import json
import sys
from pathlib import Path

RESULTS = Path(__file__).parent / "results"


def record(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        for row in rows:
            f.write(json.dumps(row, default=str) + "\n")


def _passed(path: Path) -> dict[int, bool]:
    out: dict[int, bool] = {}
    for line in path.read_text().splitlines():
        row = json.loads(line)
        out[row["case"]] = out.get(row["case"], True) and bool(row["passed"])
    return out


def compare(old: Path, new: Path) -> list[str]:
    """Case ids that passed in the old run and fail in the new one."""
    before, after = _passed(old), _passed(new)
    return [f"q{c:02d}" for c in sorted(after) if before.get(c) and not after[c]]


def main() -> int:
    files = sorted(RESULTS.glob("*.jsonl"))
    if len(files) < 2:
        print("need two result files to compare")
        return 1
    worse = compare(files[-2], files[-1])
    print("regressions: " + (", ".join(worse) if worse else "none"))
    return 1 if worse else 0


if __name__ == "__main__":
    sys.exit(main())
