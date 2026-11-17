import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from ruamel.yaml import YAML

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


FILES = {
    "profile": ("profile.yaml", Profile),
    "education": ("education.yaml", EducationFile),
    "jobs": ("jobs.yaml", JobsFile),
    "guardrails": ("guardrails.yaml", GuardrailsFile),
    "memory": ("memory.yaml", MemoryFile),
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
    raw = YAML(typ="safe").load(path.read_text()) or {}
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
    memory_ids = {m.id for m in d.memory.entries}
    for m in d.memory.entries:
        if m.replaced_by and m.replaced_by not in memory_ids:
            raise DataRepoError("memory.yaml", m.id, f"replaced_by {m.replaced_by} not found")
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


def load_data(root: Path) -> KaData:
    loaded = {key: _read(root, name, model) for key, (name, model) in FILES.items()}
    data = KaData(**loaded)
    _cross_checks(data)
    return data
