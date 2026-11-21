import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from ruamel.yaml import YAML, YAMLError

from .schemas.accounts import AccountsFile
from .schemas.categories import CategoriesFile
from .schemas.education import EducationFile
from .schemas.guardrails import GuardrailsFile
from .schemas.ids import IdsFile
from .schemas.jobs import JobsFile
from .schemas.memory import MemoryFile
from .schemas.other import OtherFile
from .schemas.profile import Profile
from .schemas.rules import MerchantRulesFile, TransactionTypesFile


class DataRepoError(Exception):
    def __init__(self, file: str, field: str | None, reason: str) -> None:
        self.file = file
        self.field = field
        super().__init__(f"{file}: {field or '-'}: {reason}")


@dataclass(frozen=True)
class KaData:
    profile: Profile
    education: EducationFile
    jobs: JobsFile
    guardrails: GuardrailsFile
    memory: MemoryFile
    accounts: AccountsFile
    categories: CategoriesFile
    merchant_rules: MerchantRulesFile
    transaction_types: TransactionTypesFile
    other: OtherFile
    ids: IdsFile
    # memory/<toolkit>.yaml for each toolkit; core memory is `memory` above
    toolkit_memory: dict[str, MemoryFile] = field(default_factory=dict)


FILES = {
    "profile": ("profile.yaml", Profile),
    "education": ("education.yaml", EducationFile),
    "jobs": ("jobs.yaml", JobsFile),
    "guardrails": ("guardrails.yaml", GuardrailsFile),
    "memory": ("memory/core.yaml", MemoryFile),
    "accounts": ("accounts.yaml", AccountsFile),
    "categories": ("categories.yaml", CategoriesFile),
    "merchant_rules": ("rules/merchants.yaml", MerchantRulesFile),
    "transaction_types": ("rules/transaction_types.yaml", TransactionTypesFile),
    "other": ("other.yaml", OtherFile),
    "ids": ("ids.yaml", IdsFile),
}


def _plain(v: Any) -> Any:
    """YAML turns bare 2024-01-15 into a date; the schemas want the string."""
    if isinstance(v, (date, datetime)):
        return v.isoformat()[:10]
    if isinstance(v, dict):
        return {k: _plain(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_plain(x) for x in v]
    return v


def _read(root: Path, name: str, model: type) -> Any:
    path = root / name
    if not path.is_file():
        raise DataRepoError(name, None, "file missing")
    try:
        raw = YAML(typ="safe").load(path.read_text()) or {}
    except YAMLError as e:
        raise DataRepoError(name, None, f"invalid YAML: {str(e).splitlines()[0]}") from e
    try:
        return model(**_plain(raw))
    except ValidationError as e:
        first = e.errors()[0]
        raise DataRepoError(name, ".".join(str(p) for p in first["loc"]), first["msg"]) from e


def _cross_checks(d: KaData) -> None:
    domain_ids = {x.id for x in d.jobs.domains}
    for job in d.jobs.jobs:
        for h in job.highlights:
            for dom in h.domains:
                if dom not in domain_ids:
                    raise DataRepoError("jobs.yaml", h.id, f"unknown domain {dom}")
    for r in d.merchant_rules.rules:
        if r.category not in d.categories.categories:
            raise DataRepoError("rules/merchants.yaml", r.id, f"unknown category {r.category}")
    memory_ids: set[str] = set()
    for name, mem in {"core": d.memory, **d.toolkit_memory}.items():
        here = {m.id for m in mem.entries}
        for m in mem.entries:
            if m.id in memory_ids:
                raise DataRepoError(f"memory/{name}.yaml", m.id, "id already used in another memory file")
            if m.replaced_by and m.replaced_by not in here:
                raise DataRepoError(f"memory/{name}.yaml", m.id, f"replaced_by {m.replaced_by} not found")
        memory_ids |= here
    in_use = {
        "E": [e.id for e in d.education.entries],
        "D": [x.id for x in d.jobs.domains],
        "H": [h.id for j in d.jobs.jobs for h in j.highlights],
        "G": [g.id for g in d.guardrails.rules],
        "M": list(memory_ids),
        "A": [a.id for a in d.accounts.accounts],
        "R": [r.id for r in d.merchant_rules.rules],
        "O": [r.id for r in d.other.records],
    }
    for prefix, ids in in_use.items():
        if not ids:
            continue
        top = max(int(re.split(r"-", i)[1]) for i in ids)
        if d.ids.next.get(prefix, 0) <= top:
            raise DataRepoError("ids.yaml", prefix, f"next counter must exceed {prefix}-{top}")


def memory_files(root: Path) -> list[str]:
    """Toolkit memory files present in the repo (core excluded)."""
    folder = root / "memory"
    return sorted(p.stem for p in folder.glob("*.yaml") if p.stem != "core") if folder.is_dir() else []


def load_memory(root: Path, toolkit: str) -> MemoryFile:
    """One memory file; a toolkit with no file yet has no memories."""
    if not re.fullmatch(r"[a-z]+", toolkit):
        raise DataRepoError("memory", None, f"bad memory name {toolkit!r}")
    if not (root / "memory" / f"{toolkit}.yaml").is_file():
        return MemoryFile()
    return _read(root, f"memory/{toolkit}.yaml", MemoryFile)


def load_data(root: Path) -> KaData:
    loaded = {key: _read(root, name, model) for key, (name, model) in FILES.items()}
    loaded["toolkit_memory"] = {n: load_memory(root, n) for n in memory_files(root)}
    data = KaData(**loaded)
    _cross_checks(data)
    return data
