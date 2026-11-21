"""Safe edits to the data repo: patch, validate the whole repo, diff in memory, then lock and commit."""

import difflib
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any, Literal

from pydantic import Field
from ruamel.yaml import YAML

from server.locks import repo_lock

from .loader import DataRepoError, load_data
from .schemas.common import KaModel

Target = Literal[
    "profile", "education", "domain", "job", "highlight", "guardrail",
    "memory", "account", "merchant_rule", "other_record", "transaction_type",
]  # fmt: skip

# target -> (file, list key in that file, id prefix, id width). Jobs have no id; profile is a mapping.
LISTS = {
    "education": ("education.yaml", "entries", "E", 2),
    "domain": ("jobs.yaml", "domains", "D", 2),
    "job": ("jobs.yaml", "jobs", "", 0),
    "highlight": ("jobs.yaml", "jobs", "H", 3),
    "guardrail": ("guardrails.yaml", "rules", "G", 2),
    "memory": ("memory/core.yaml", "entries", "M", 4),
    "account": ("accounts.yaml", "accounts", "A", 2),
    "merchant_rule": ("rules/merchants.yaml", "rules", "R", 3),
    "other_record": ("other.yaml", "records", "O", 3),
    "transaction_type": ("rules/transaction_types.yaml", "types", "", 0),
}
# Records without an id, found by a natural key instead; KEY_FIELDS cannot change on update.
KEY_FIELDS = {"job": {"company", "start"}, "transaction_type": {"bank", "type_text"}}
NATURAL_KEYS = {
    "job": lambda r: f"{r.get('company')}|{r.get('start')}",
    "transaction_type": lambda r: f"{r.get('bank')}|{r.get('type_text')}",
}
RETIRE = {"highlight": ("retired", True), "memory": ("status", "retired")}


class ChangeError(Exception):
    """Bad patch, failed validation, dirty or stale file. The message goes back to the model."""


class Patch(KaModel):
    target: Target
    op: Literal["add", "update", "retire", "delete"]
    key: str | None = None  # record id; job key "Company|start"; omitted for add and profile
    parent: str | None = None  # job key, required when adding a highlight
    scope: str = Field(default="core", pattern=r"^[a-z]+$")  # memory file: memory/<scope>.yaml
    fields: dict[str, Any] = {}


@dataclass
class ChangePlan:
    files: dict[str, tuple[str, str]]  # relative path -> (old text, new text)
    diff: str
    message: str
    key: str  # id of the record touched or created


_yaml = YAML()
_yaml.preserve_quotes = True
_yaml.width = 4096
_yaml.indent(mapping=2, sequence=4, offset=2)


def load_text(text: str) -> Any:
    return _yaml.load(text)


def dump_text(doc: Any) -> str:
    out = StringIO()
    _yaml.dump(doc, out)
    return out.getvalue()


def _git(root: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
    )
    if done.returncode != 0:
        first = (done.stderr.strip().splitlines() or ["git failed"])[0]
        raise ChangeError(f"git {args[0]}: {first}")
    return done.stdout.strip()


def _check_clean(root: Path, paths: list[str]) -> None:
    for path in paths:
        if _git(root, "status", "--porcelain", "--", path):
            raise ChangeError(f"{path} has uncommitted changes")


def _find(items: list, key: str, natural_key: bool, what: str) -> Any:
    natural = NATURAL_KEYS.get(what) if natural_key else None
    for item in items:
        if (natural(item) if natural else str(item.get("id"))) == key:
            return item
    raise ChangeError(f"{what} not found: {key}")


class _Editor:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.old: dict[str, str] = {}
        self.docs: dict[str, Any] = {}

    def doc(self, path: str) -> Any:
        if path not in self.docs:
            self.old[path] = (self.root / path).read_text()
            self.docs[path] = load_text(self.old[path])
        return self.docs[path]

    def new_id(self, prefix: str, width: int) -> str:
        counters = self.doc("ids.yaml")["next"]
        n = counters.get(prefix, 1)  # no counter yet means no ids of this kind exist
        counters[prefix] = n + 1
        return f"{prefix}-{n:0{width}d}"


def _edit(ed: _Editor, p: Patch) -> str:
    """Apply the patch to the in-memory documents; return the key used in the commit message."""
    if "id" in p.fields:
        raise ChangeError("id is assigned by the system and cannot be set or changed")
    if p.target == "job" and "highlights" in p.fields:
        raise ChangeError("edit highlights with target=highlight; job edits cannot carry them")
    if p.target == "profile":
        if p.op != "update":
            raise ChangeError("profile supports update only")
        profile = ed.doc("profile.yaml")
        for k, v in p.fields.items():
            profile[k] = v
        return "profile"

    path, list_key, prefix, width = LISTS[p.target]
    if p.target == "memory":
        path = f"memory/{p.scope}.yaml"
        if not (ed.root / path).is_file():
            raise ChangeError(f"no memory file for {p.scope}")
    doc = ed.doc(path)
    if doc is None:
        raise ChangeError(f"{path} is empty; add its structure by hand first")
    if p.op == "add" and doc.get(list_key) is None:
        doc[list_key] = []
    is_job, is_highlight = p.target in NATURAL_KEYS, p.target == "highlight"
    items = doc.get(list_key)
    if items is None:  # only reachable for update, retire and delete: nothing to find
        items = []

    if p.op == "add":
        if is_highlight:
            if not p.parent:
                raise ChangeError("adding a highlight needs parent (the job key)")
            job = _find(items, p.parent, True, "job")
            target_list = job.setdefault("highlights", [])
        else:
            target_list = items
        if is_job:
            record = dict(p.fields)
            key = NATURAL_KEYS[p.target](record)
        else:
            key = ed.new_id(prefix, width)
            record = {"id": key, **p.fields}
        target_list.append(record)
        return key

    if not p.key:
        raise ChangeError(f"{p.op} needs key")
    if is_highlight:
        holder = next(
            (
                j["highlights"]
                for j in items
                if any(str(h["id"]) == p.key for h in j.get("highlights") or [])
            ),
            None,
        )
        if holder is None:
            raise ChangeError(f"highlight not found: {p.key}")
        record, container = _find(holder, p.key, False, "highlight"), holder
    else:
        record, container = _find(items, p.key, is_job, p.target), items

    if p.op == "update":
        identity = KEY_FIELDS.get(p.target, set()) & set(p.fields)
        if identity:
            names = " and ".join(sorted(KEY_FIELDS[p.target]))
            raise ChangeError(f"{names} identify a {p.target}; delete and re-add")
        for k, v in p.fields.items():
            record[k] = v
    elif p.op == "retire":
        if p.target not in RETIRE:
            raise ChangeError(f"cannot retire {p.target}; use delete")
        field, value = RETIRE[p.target]
        record[field] = value
    else:
        container.remove(record)
    return p.key


def _finish_plan(root: Path, ed: _Editor, message: str, key: str) -> ChangePlan:
    new = {path: dump_text(doc) for path, doc in ed.docs.items()}
    changed = {path: (ed.old[path], text) for path, text in new.items() if text != ed.old[path]}
    if not changed:
        raise ChangeError("patch changes nothing")
    _check_clean(root, list(changed))
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "repo"
        shutil.copytree(root, copy, ignore=shutil.ignore_patterns(".git", "local"))
        for path, (_, text) in changed.items():
            (copy / path).write_text(text)
        try:
            load_data(copy)
        except DataRepoError as e:
            raise ChangeError(f"change rejected: {e}") from e
    diff = "".join(
        "".join(
            difflib.unified_diff(
                old.splitlines(True), text.splitlines(True), f"a/{path}", f"b/{path}"
            )
        )
        for path, (old, text) in sorted(changed.items())
    )
    return ChangePlan(files=changed, diff=diff, message=message, key=key)


def plan_change(root: Path, patch: Patch) -> ChangePlan:
    ed = _Editor(root)
    key = _edit(ed, patch)
    return _finish_plan(root, ed, f"data: {patch.op} {patch.target} {key}", key)


def plan_batch(root: Path, patches: list[Patch], message: str) -> ChangePlan:
    """Several patches, applied in order on one in-memory copy, validated once, committed once."""
    if not patches:
        raise ChangeError("nothing to change")
    ed = _Editor(root)
    keys = [_edit(ed, p) for p in patches]
    return _finish_plan(root, ed, message, ",".join(keys))


def apply_change(root: Path, plan: ChangePlan) -> str:
    paths = sorted(plan.files)
    # every account's folder is in one git repo: one lock at its top, so commits never overlap
    with repo_lock(Path(_git(root, "rev-parse", "--show-toplevel"))):
        for path, (old, _) in plan.files.items():
            if (root / path).read_text() != old:
                raise ChangeError(f"{path} changed since proposal")
        _check_clean(root, paths)
        try:
            for path, (_, new) in plan.files.items():
                (root / path).write_text(new)
            try:
                load_data(
                    root
                )  # a hand edit elsewhere since the proposal can break cross-file rules
            except DataRepoError as e:
                raise ChangeError(f"change rejected: {e}") from e
            _git(root, "add", "--", *paths)
            _git(root, "commit", "-q", "-m", plan.message, "--", *paths)
        except Exception:
            for path, (old, _) in plan.files.items():
                (root / path).write_text(old)
            subprocess.run(
                ["git", "-C", str(root), "reset", "-q", "--", *paths],
                capture_output=True,
                check=False,
            )
            raise
        return _git(root, "rev-parse", "--short", "HEAD")
