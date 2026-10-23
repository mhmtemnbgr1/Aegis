"""GitHub Actions ortamından pull request olayını okur."""

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class EventError(RuntimeError):
    pass


class PullRequestEvent(BaseModel):
    event_name: str
    repository: str
    number: int
    title: str = ""
    body: str = ""
    base_ref: str
    base_sha: str
    head_sha: str
    is_fork: bool = False

    @property
    def metadata(self) -> str:
        """Analize güvenilmeyen veri olarak verilecek PR başlığı ve açıklaması."""
        return f"{self.title}\n\n{self.body}".strip()


def load_event(env: Mapping[str, str] | None = None) -> PullRequestEvent:
    env = os.environ if env is None else env
    event_name = env.get("GITHUB_EVENT_NAME", "")
    if event_name == "pull_request_target":
        raise EventError(
            "pull_request_target desteklenmez: fork kodu gizli anahtarlarla çalışabilir. "
            "Workflow'u `on: pull_request` ile tetikleyin."
        )
    if event_name != "pull_request":
        raise EventError(f"desteklenmeyen olay: {event_name or '(yok)'}")
    path = env.get("GITHUB_EVENT_PATH")
    if not path:
        raise EventError("GITHUB_EVENT_PATH tanımlı değil")
    payload: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
    pr = payload["pull_request"]
    head_repo = (pr["head"].get("repo") or {}).get("full_name")
    base_repo = pr["base"]["repo"]["full_name"]
    return PullRequestEvent(
        event_name=event_name,
        repository=env.get("GITHUB_REPOSITORY", base_repo),
        number=pr["number"],
        title=pr.get("title") or "",
        body=pr.get("body") or "",
        base_ref=pr["base"]["ref"],
        base_sha=pr["base"]["sha"],
        head_sha=pr["head"]["sha"],
        is_fork=head_repo != base_repo,
    )
