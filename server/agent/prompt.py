"""System prompt: principles from prompt.md, today's date, a short core profile, the toolkit
index, guardrails and core memory. Toolkit instructions and memory arrive with load_toolkit,
so this text stays the same for the whole chat (and caches well)."""

from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Protocol

from server.integrations.data_repo.loader import KaData

RULES = (Path(__file__).parent / "prompt.md").read_text()
WEB_OFF = (
    "Web search is off in this setup: you cannot search or read the web. For news, prices or "
    "anything current, say web search is turned off (flag web_search in config.yaml); never offer to "
    "look it up."
)


class Listed(Protocol):
    name: str
    description: str


def build_system_prompt(
    data: KaData, today: date, toolkits: Sequence[Listed] = (), web: bool = True
) -> str:
    p = data.profile
    active = [m for m in data.memory.entries if m.status == "active"]
    profile = [f"Name: {p.name}"]
    if p.location:
        where = ", ".join(x for x in (p.location.city, p.location.region, p.location.country) if x)
        if where:
            profile.append(f"Location: {where}")
    if p.timezone:
        profile.append(f"Time zone: {p.timezone}")
    prefs = [f"{m.text} ({m.id})" for m in active if m.type == "preference"]
    if prefs:
        profile.append("Main preferences: " + "; ".join(prefs))
    guardrails = [
        f"- {g.id} [{g.kind}, scope {g.scope}]: {g.text}" + (f" ({g.reason})" if g.reason else "")
        for g in data.guardrails.rules
    ] or ["- none"]
    memory = [f"- {m.id} [{m.type}]: {m.text}" for m in active if m.type != "preference"] or [
        "- none"
    ]
    index = [f"- {t.name}: {t.description}" for t in toolkits] or ["- none"]
    return "\n\n".join(
        [
            RULES.strip(),
            f"Today is {today:%A} {today.isoformat()}.",
            "About the owner:\n" + "\n".join(profile),
            "Toolkits you can load with load_toolkit (load one only when the question is about its "
            "subject; never load finance for news, people or general questions):\n"
            + "\n".join(index),
            *([] if web else [WEB_OFF]),
            "Guardrails (always obey):\n" + "\n".join(guardrails),
            "What you remember about the owner:\n" + "\n".join(memory),
        ]
    )
