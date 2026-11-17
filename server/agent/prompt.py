"""System prompt: fixed rules from prompt.md plus the owner's profile, guardrails and memory."""

from datetime import date
from pathlib import Path

from server.integrations.data_repo.loader import KaData

RULES = (Path(__file__).parent / "prompt.md").read_text()


def build_system_prompt(data: KaData, today: date) -> str:
    p = data.profile
    where = (
        ", ".join(x for x in (p.location.city, p.location.region, p.location.country) if x)
        if p.location
        else ""
    )
    profile = [f"Name: {p.name}"]
    if where:
        profile.append(f"Location: {where}")
    if p.summary:
        profile.append(f"Summary: {p.summary}")
    guardrails = [
        f"- {g.id} [{g.kind}, scope {g.scope}]: {g.text}" + (f" ({g.reason})" if g.reason else "")
        for g in data.guardrails.rules
    ] or ["- none"]
    memory = [
        f"- {m.id} [{m.type}]: {m.text}" for m in data.memory.entries if m.status == "active"
    ] or ["- none"]
    return "\n\n".join(
        [
            RULES.strip(),
            f"Today is {today.isoformat()}.",
            "About the owner:\n" + "\n".join(profile),
            "Guardrails (always obey):\n" + "\n".join(guardrails),
            "What you remember about the owner:\n" + "\n".join(memory),
        ]
    )
