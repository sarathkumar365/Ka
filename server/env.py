"""Minimal .env reader. Values go to os.environ only; nothing is logged.

The file wins over variables already exported in the shell: a stale exported key otherwise
silently beats the one the owner put in .env.
"""

import os
from pathlib import Path


def load_env(path: Path = Path(".env")) -> None:
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ[key.strip()] = value.strip().strip("'\"")
