"""Turn a draft into by-job Pending cards. Nothing here writes to the data repo."""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from server.integrations.data_repo.loader import KaData
from server.integrations.data_repo.writer import Patch
from server.memory.pending import queue_memory
from server.store.db import Db

from .draft import DraftHighlight, DraftJob, ResumeDraft

KIND = "bundle"
LEVELS = {"primary", "secondary", "bachelor", "master", "postgrad_certificate", "certification"}


@dataclass
class QueueResult:
    cards: int = 0
    skipped: list[str] = field(default_factory=list)


PARTIAL = re.compile(r"^\d{4}-(0[1-9]|1[0-2])(-\d{2})?$")


def _one_line(text: str) -> str:
    """Titles and labels reach commit messages and the screen: one line, bounded."""
    return " ".join(text.split())[:200]


def _date_problem(job: DraftJob) -> str | None:
    if not job.start:
        return "no start date found"
    if not PARTIAL.match(job.start):
        return f"start date not understood: {_one_line(job.start)}"
    if job.end and not PARTIAL.match(job.end):
        return f"end date not understood: {_one_line(job.end)}"
    if job.end and job.end < job.start:
        return "end date is before the start date"
    return None


def _norm(text: str) -> str:
    return re.sub(r"\W+", " ", text.lower()).strip()


def _item(n: int, label: str, detail: str, patch: Patch) -> dict[str, Any]:
    return {
        "id": f"i{n}",
        "label": label,
        "detail": detail,
        "selected": True,
        "patch": patch.model_dump(),
    }


def _card(
    db: Db,
    now: datetime,
    source: str,
    section: str,
    title: str,
    items: list[dict],
    key: str,
    needs: list[int] | None = None,
    blocked: str | None = None,
    job_id: str | None = None,
) -> int | None:
    if not items or db.pending_exists(KIND, key):
        return None
    payload = {
        "title": title,
        "section": section,
        "needs": needs or [],
        "job_id": job_id,
        "blocked": blocked,
        "note": None,
        "items": items,
    }
    return db.add_pending(KIND, payload, source, now, key)


def _basics_items(data: KaData, draft: ResumeDraft) -> list[dict]:
    p, have = draft.profile, data.profile
    items: list[dict] = []

    def add(field_name: str, label: str, detail: str, value: Any) -> None:
        patch = Patch(target="profile", op="update", fields={field_name: value})
        items.append(_item(len(items) + 1, label, detail, patch))

    if p.name and _norm(p.name) != _norm(have.name):
        add("name", f"Name: {p.name}", f"was {have.name}", p.name)
    new_emails = [e for e in p.emails if e.lower() not in {x.address.lower() for x in have.emails}]
    if new_emails:
        merged = [e.model_dump() for e in have.emails] + [
            {"address": e, "label": ""} for e in new_emails
        ]
        add("emails", "Emails: " + ", ".join(new_emails), "added to the ones you have", merged)
    new_phones = [x for x in p.phones if _norm(x) not in {_norm(h.number) for h in have.phones}]
    if new_phones:
        merged = [x.model_dump() for x in have.phones] + [
            {"number": x, "label": ""} for x in new_phones
        ]
        add("phones", "Phones: " + ", ".join(new_phones), "added to the ones you have", merged)
    if p.location and any(p.location.values()):
        loc = {k: v for k, v in p.location.items() if k in ("city", "region", "country") and v}
        old = have.location.model_dump() if have.location else {}
        if any(old.get(k) != v for k, v in loc.items()):
            add(
                "location",
                "Location: " + ", ".join(loc.values()),
                "was " + (", ".join(v for v in old.values() if v) or "empty"),
                {**old, **loc},
            )
    new_links = [
        lk for lk in p.links if lk.get("url") and lk["url"] not in {h.url for h in have.links}
    ]
    if new_links:
        merged = [x.model_dump() for x in have.links] + [
            {"label": lk.get("label", ""), "url": lk["url"]} for lk in new_links
        ]
        add("links", "Links: " + ", ".join(lk["url"] for lk in new_links), "added", merged)
    known_langs = {_norm(x.name) for x in have.languages}
    new_langs = [x for x in p.languages if x.get("name") and _norm(x["name"]) not in known_langs]
    if new_langs:
        merged = [x.model_dump() for x in have.languages] + [
            {"name": x["name"], "level": x.get("level", "")} for x in new_langs
        ]
        add("languages", "Languages: " + ", ".join(x["name"] for x in new_langs), "added", merged)
    return items


def _education_items(data: KaData, draft: ResumeDraft, skipped: list[str]) -> list[dict]:
    have = {(_norm(e.institution), _norm(e.program)) for e in data.education.entries}
    items: list[dict] = []
    for e in draft.education:
        if (_norm(e.institution), _norm(e.program)) in have:
            continue
        level = e.level.strip().lower()
        if level not in LEVELS:
            skipped.append(f"education {e.program}: unknown level {e.level!r}")
            continue
        fields = {k: v for k, v in e.model_dump().items() if v not in (None, "")}
        fields["level"] = level
        for k in ("start", "end"):  # an unreadable date is left out rather than failing the card
            if k in fields and not PARTIAL.match(fields[k]):
                del fields[k]
        patch = Patch(target="education", op="add", fields=fields)
        dates = " to ".join(x for x in (e.start, e.end) if x)
        items.append(
            _item(
                len(items) + 1,
                _one_line(f"{e.program}, {e.institution}"),
                f"{level} {dates}".strip(),
                patch,
            )
        )
    return items


def _domain_names(draft: ResumeDraft) -> list[str]:
    names = list(draft.domains)
    for job in draft.jobs:
        for h in job.highlights:
            names.extend(h.domains)
    seen: dict[str, str] = {}
    for n in names:
        if n.strip():
            seen.setdefault(_norm(n), n.strip())
    return list(seen.values())


def _highlight_item(n: int, h: DraftHighlight, key: str) -> dict:
    fields: dict[str, Any] = {"text": _one_line(h.text)}
    if h.tech:
        fields["tech"] = h.tech
    if h.domains:
        fields["domains"] = h.domains
    if h.numbers:
        fields["numbers"] = [
            {"value": str(x.value), "unit": x.unit, "label": x.label} for x in h.numbers
        ]
    detail = " · ".join([*h.tech, *h.domains, *(f"{x.value} {x.unit}".strip() for x in h.numbers)])
    patch = Patch(target="highlight", op="add", parent=key, fields=fields)
    return _item(n, _one_line(h.text), detail, patch)


def _job_items(job: DraftJob, key: str) -> list[dict]:
    assumed = job.employment_type is None
    fields: dict[str, Any] = {
        "company": _one_line(job.company),
        "position": _one_line(job.position),
        "employment_type": job.employment_type or "full_time",
    }
    for k in ("location", "start", "end", "summary"):
        if getattr(job, k):
            fields[k] = _one_line(getattr(job, k))
    span = f"{job.start or '?'} to {job.end or 'now'}"
    detail = span + (" · full time (assumed)" if assumed else f" · {fields['employment_type']}")
    items = [
        _item(
            1,
            _one_line(f"{job.company} · {job.position}"),
            detail,
            Patch(target="job", op="add", fields=fields),
        )
    ]
    for h in job.highlights:
        items.append(_highlight_item(len(items) + 1, h, key))
    return items


def queue_draft(
    db: Db, data: KaData, draft: ResumeDraft, source: str, now: datetime, job_id: str | None = None
) -> QueueResult:
    result = QueueResult()

    def add(**kw) -> int | None:
        cid = _card(db, now, source, job_id=job_id, **kw)
        if cid is not None:
            result.cards += 1
        return cid

    add(
        section="basics",
        title="Your basics",
        items=_basics_items(data, draft),
        key="bundle:basics:" + source,
    )
    edu = _education_items(data, draft, result.skipped)
    add(section="education", title="Education", items=edu, key="bundle:education:" + source)

    stored_domains = {_norm(d.name) for d in data.jobs.domains}
    new_names = [n for n in _domain_names(draft) if _norm(n) not in stored_domains]
    domain_items = [
        _item(
            i + 1,
            n,
            "new domain",
            Patch(target="domain", op="add", fields={"name": n, "description": ""}),
        )
        for i, n in enumerate(new_names)
    ]
    domains_id = add(
        section="domains", title="Domains", items=domain_items, key="bundle:domains:" + source
    )
    needs = [domains_id] if domains_id else []

    stored = {f"{_norm(j.company)}|{j.start}": j for j in data.jobs.jobs}
    for job in draft.jobs:
        key = f"{job.company}|{job.start}"
        card_key = f"bundle:job:{_norm(job.company)}|{job.start}"
        known = stored.get(f"{_norm(job.company)}|{job.start}")
        if known is not None:
            have = {_norm(h.text) for h in known.highlights}
            fresh = [h for h in job.highlights if _norm(h.text) not in have]
            if not fresh:
                result.skipped.append(f"{job.company} is already stored")
                continue
            items = [
                _highlight_item(i + 1, h, f"{known.company}|{known.start}")
                for i, h in enumerate(fresh)
            ]
            add(
                section="highlights",
                title=_one_line(
                    f"Add {len(fresh)} highlight{'s' if len(fresh) != 1 else ''} to {job.company}"
                ),
                items=items,
                key=card_key + ":highlights:" + "|".join(sorted(_norm(h.text) for h in fresh)),
                needs=needs,
            )
            continue
        add(
            section="job",
            title=_one_line(f"{job.company}, {job.position}"),
            items=_job_items(job, key),
            key=card_key,
            needs=needs,
            blocked=_date_problem(job),
        )
    return result


def queue_basics(
    db: Db, data: KaData, name: str, city: str, region: str, country: str, role: str, now: datetime
) -> int:
    queued = 0
    draft = ResumeDraft.model_validate(
        {
            "profile": {
                "name": name or None,
                "location": {"city": city, "region": region, "country": country},
            }
        }
    )
    items = _basics_items(data, draft)
    if role and not data.profile.summary:
        patch = Patch(target="profile", op="update", fields={"summary": role})
        items.append(_item(len(items) + 1, f"Summary: {role}", "your current work", patch))
    elif role:
        queued += bool(
            queue_memory(db, data, f"Works as {role}", "fact", None, "onboarding", now)["queued"]
        )
    if items and _card(
        db,
        now,
        "onboarding",
        "basics",
        "Your basics",
        items,
        "bundle:basics:onboarding:" + name + role,
    ):
        queued += 1
    return queued
