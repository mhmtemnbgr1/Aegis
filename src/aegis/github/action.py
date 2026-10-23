"""GitHub Action giriş noktası (`aegis github`).

Güvenlik kuralları (docs/architecture.md §7):
- Yalnızca `pull_request` olayında çalışır; `pull_request_target` reddedilir.
- Yapılandırma ve `.aegisignore` PR'ın değil taban commit'in sürümünden okunur; PR yazarı
  kendi kodunu incelemeden saklayamaz.
- Fork PR'larında yalnızca gatekeeper ve yerel model (Ollama) çalışır.
- Hiçbir hata PR'ı bloklamaz: süreç her durumda 0 ile çıkar (fail-open).
"""

import logging
import os
from collections.abc import Callable, Mapping
from pathlib import Path

from pathspec import GitIgnoreSpec
from pydantic import ValidationError

from aegis.config import CONFIG_FILE, AegisConfig, parse_config
from aegis.diff import git_commit_messages, git_diff, git_show
from aegis.diff.filters import AEGISIGNORE
from aegis.github.client import API_URL, GitHubClient
from aegis.github.event import EventError, PullRequestEvent, load_event
from aegis.github.publisher import publish
from aegis.github.render import render_summary
from aegis.llm import ResponseCache
from aegis.review import ANALYST, ReviewResult, ReviewStatus, run_review
from aegis.telemetry.runs import append_run

log = logging.getLogger(__name__)

ClientFactory = Callable[[str, str, str], GitHubClient]


def _default_client(token: str, repository: str, api_url: str) -> GitHubClient:
    return GitHubClient(token, repository, api_url=api_url)


def base_config(event: PullRequestEvent, repo: Path, config_path: str) -> AegisConfig:
    """Taban commit'teki yapılandırma; yoksa varsayılanlar."""
    text = git_show(event.base_sha, config_path, repo)
    return parse_config(text) if text is not None else AegisConfig()


def base_ignore(event: PullRequestEvent, repo: Path) -> GitIgnoreSpec:
    text = git_show(event.base_sha, AEGISIGNORE, repo) or ""
    return GitIgnoreSpec.from_lines(text.splitlines())


def llm_allowed(event: PullRequestEvent, config: AegisConfig) -> bool:
    """Fork PR'larında gizli anahtar yoktur ve kod dışarı gönderilmez: yalnızca yerel model."""
    if not config.review.llm_enabled:
        return False
    return not event.is_fork or config.agent(ANALYST).provider == "ollama"


def _error_result(error: str) -> ReviewResult:
    return ReviewResult(status=ReviewStatus.ERROR, error=error)


def _write_step_summary(env: Mapping[str, str], body: str) -> None:
    path = env.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(body + "\n")
    except OSError:
        pass


def run_action(
    *,
    repo: Path = Path("."),
    config_path: str = CONFIG_FILE,
    json_out: Path | None = None,
    env: Mapping[str, str] | None = None,
    client_factory: ClientFactory = _default_client,
) -> int:
    env = os.environ if env is None else env
    try:
        event = load_event(env)
    except (EventError, OSError, KeyError, ValueError) as exc:
        log.error("Aegis çalıştırılmadı: %s", exc)
        _write_step_summary(env, f"⚠️ Aegis çalıştırılmadı: {exc}")
        return 0

    try:
        config = base_config(event, repo, config_path)
    except (ValidationError, ValueError) as exc:
        config = None
        result = _error_result(f"yapılandırma okunamadı ({config_path}): {exc}")

    if config is not None:
        try:
            diff_text = git_diff(event.base_sha, event.head_sha, repo=repo)
            commits = git_commit_messages(event.base_sha, event.head_sha, repo=repo)
        except Exception as exc:  # ör. checkout'ta fetch-depth: 0 eksik
            result = _error_result(f"git diff alınamadı: {exc}")
        else:
            result = run_review(
                diff_text,
                config,
                ignore=base_ignore(event, repo),
                metadata=f"{event.metadata}\n\n{commits}".strip(),
                llm_enabled=llm_allowed(event, config),
                cache=ResponseCache(repo / config.review.cache_dir),
            )
        append_run(
            repo / config.review.runs_path,
            result,
            source="action",
            pr=event.number,
            fork=event.is_fork,
        )

    summary = render_summary(result)
    _write_step_summary(env, summary)
    if json_out is not None:
        try:
            json_out.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        except OSError as exc:
            log.warning("sonuç dosyası yazılamadı: %s", exc)

    token = env.get("GITHUB_TOKEN")
    if not token:
        log.warning("GITHUB_TOKEN yok; PR'a yorum yazılmadı")
        return 0
    try:
        client = client_factory(token, event.repository, env.get("GITHUB_API_URL", API_URL))
        report = publish(client, event.number, event.head_sha, result)
        log.info(
            "yayın: özet=%s, yeni=%d, mevcut=%d, çözüldü=%d, check=%s",
            report.summary_comment,
            report.posted,
            report.skipped_existing,
            report.resolved,
            report.check_conclusion,
        )
    except Exception:  # fail-open
        log.exception("GitHub yayını başarısız")
    return 0
