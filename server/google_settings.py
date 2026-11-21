"""An account's own Drive folder and Sheet ids, kept in users/<id>/settings.yaml."""

import subprocess

from ruamel.yaml import YAML

from server.config import Config
from server.locks import repo_lock


def save_google_settings(cfg: Config, drive_folder_id: str | None, sheet_id: str | None) -> None:
    path = cfg.data_repo / "settings.yaml"
    yaml = YAML()
    current = (yaml.load(path.read_text()) or {}) if path.is_file() else {}
    for key, value in (("drive_folder_id", drive_folder_id), ("sheet_id", sheet_id)):
        if value:
            current[key] = value
        else:
            current.pop(key, None)
    base = cfg.repo_root or cfg.data_repo
    with repo_lock(base):
        with path.open("w") as f:
            yaml.dump(dict(current), f)
        rel = str(path.relative_to(base))
        tracked = subprocess.run(
            ["git", "-C", str(base), "ls-files", "--error-unmatch", rel],
            check=False, capture_output=True,
        ).returncode == 0  # fmt: skip
        unchanged = tracked and subprocess.run(
            ["git", "-C", str(base), "diff", "--quiet", "--", rel], check=False
        ).returncode == 0
        if unchanged:
            return
        for args in (["add", "--", rel], ["commit", "-q", "-m", "data: google settings", "--", rel]):
            done = subprocess.run(["git", "-C", str(base), *args], check=False, capture_output=True, text=True)
            if done.returncode != 0:
                raise RuntimeError(f"git {args[0]} failed")
