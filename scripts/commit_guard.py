"""Blocks commits that contain personal data, secrets, .env files or stray PDFs."""

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal

SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"AIza[0-9A-Za-z_-]{35}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]
MIN_DENYLIST_LEN = 4


@dataclass
class Violation:
    path: str
    rule: Literal["env_file", "pdf", "secret", "denylist"]
    detail: str


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s.casefold())


def find_violations(files: dict[str, bytes], denylist: list[str]) -> list[Violation]:
    entries = [
        (i + 1, _norm(e))
        for i, e in enumerate(denylist)
        if e.strip() and not e.startswith("#") and len(_norm(e)) >= MIN_DENYLIST_LEN
    ]
    out: list[Violation] = []
    for path, content in files.items():
        p = PurePosixPath(path)
        if p.name == ".env" or (p.name.startswith(".env.") and p.name != ".env.example"):
            out.append(Violation(path, "env_file", "env files must not be committed"))
        if p.suffix.lower() == ".pdf":  # compressed text hides personal data from the scan
            out.append(
                Violation(path, "pdf", "PDFs are never committed; tests build them on the fly")
            )
        text = content.decode("utf-8", errors="replace")
        for pat in SECRET_PATTERNS:
            if pat.search(text):
                out.append(Violation(path, "secret", f"matches {pat.pattern[:12]}..."))
        flat = _norm(text)
        for line_no, entry in entries:
            if entry in flat:
                out.append(Violation(path, "denylist", f"denylist line {line_no}"))
    return out


def _git(*args: str) -> bytes:
    return subprocess.run(["git", *args], capture_output=True, check=True).stdout


def main() -> int:
    from server.config import ConfigError, load_config

    names = (
        _git("diff", "--cached", "--name-only", "--no-renames", "--diff-filter=ACM")
        .decode()
        .splitlines()
    )
    files = {n: _git("show", f":{n}") for n in names}
    denylist: list[str] = []
    try:
        cfg = load_config()
        if cfg.denylist_path.is_file():
            denylist = cfg.denylist_path.read_text().splitlines()
        else:
            print(f"warning: no denylist at {cfg.denylist_path}", file=sys.stderr)
    except ConfigError as e:
        print(f"BLOCKED: cannot load the denylist because of config: {e}")
        return 1
    violations = find_violations(files, denylist)
    for v in violations:
        print(f"BLOCKED {v.path}: {v.rule}: {v.detail}")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
