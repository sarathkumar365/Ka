"""Feature flags: the one list of known flags and the one way to check them."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from fastapi import HTTPException, Request

if TYPE_CHECKING:
    from server.config import Config


@dataclass(frozen=True)
class FlagInfo:
    description: str


FLAGS: dict[str, FlagInfo] = {
    "nightly_extraction": FlagInfo("Nightly memory extraction from the day's chats"),
    "web_ui": FlagInfo("Web app served by ka serve"),
    "intake": FlagInfo("Onboarding intake of resumes and memory exports"),
    "category_suggestions": FlagInfo("Model-suggested categories for new merchants"),
    "private_routing": FlagInfo("Finance chats go to the private model chain"),
    "google": FlagInfo("Drive statement inbox and Sheet copy"),
    "tracing": FlagInfo("OpenTelemetry traces to Langfuse"),
    "web_search": FlagInfo("Web search and page reading"),
    "movies": FlagInfo("Movies toolkit (TMDB)"),
    "loops": FlagInfo("Scheduled tasks that run on their own"),
}


def is_on(cfg: "Config", name: str) -> bool:
    if name not in FLAGS:
        raise KeyError(f"unknown flag: {name}")
    return bool(cfg.flags.get(name, False))


def require_flag(name: str):
    """FastAPI dependency: the route does not exist while its flag is off."""

    def check(request: Request) -> None:
        if not is_on(request.app.state.cfg, name):
            raise HTTPException(404, "not found")

    return check
