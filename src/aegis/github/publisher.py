"""İnceleme sonucunu PR'a yayınlar: tek özet yorumu, satır yorumları ve check run.

Hiçbir GitHub hatası dışarı sızmaz; yayınlanamayan parçalar loglanır ve kalanlar denenir.
"""

import logging
from typing import Any

from pydantic import BaseModel, Field

from aegis.github.client import GitHubClient, GitHubError
from aegis.github.render import (
    SUMMARY_MARKER,
    fingerprint,
    parse_finding_marker,
    render_finding,
    render_resolved,
    render_summary,
)
from aegis.models import Finding
from aegis.review import ReviewResult

log = logging.getLogger(__name__)

CHECK_NAME = "Aegis"


class PublishReport(BaseModel):
    summary_comment: str | None = None
    """`created` / `updated` / None (başarısız)."""
    posted: int = 0
    skipped_existing: int = 0
    resolved: int = 0
    check_conclusion: str | None = None
    errors: list[str] = Field(default_factory=list)


def upsert_summary(client: GitHubClient, number: int, body: str) -> str:
    """Aegis'in özet yorumu varsa günceller, yoksa oluşturur (tekrar eden yorum açılmaz)."""
    for comment in client.list_issue_comments(number):
        if SUMMARY_MARKER in (comment.get("body") or ""):
            client.update_issue_comment(comment["id"], body)
            return "updated"
    client.create_issue_comment(number, body)
    return "created"


def _comment_payload(f: Finding) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "path": f.file,
        "line": f.last_line,
        "side": "RIGHT",
        "body": render_finding(f),
    }
    if f.end_line is not None and f.end_line > f.line:
        payload["start_line"] = f.line
        payload["start_side"] = "RIGHT"
    return payload


def publish_findings(
    client: GitHubClient, number: int, head_sha: str, findings: list[Finding], report: PublishReport
) -> None:
    """Yeni bulguları satır yorumu olarak yazar, mevcutları tekrarlamaz, kaybolanları işaretler."""
    existing: dict[str, tuple[int, str, bool]] = {}
    for comment in client.list_review_comments(number):
        parsed = parse_finding_marker(comment.get("body") or "")
        if parsed is not None:
            fp, resolved = parsed
            existing[fp] = (comment["id"], comment["body"], resolved)

    current = {fingerprint(f): f for f in findings}
    new = [f for fp, f in current.items() if fp not in existing or existing[fp][2]]
    report.skipped_existing = len(current) - len(new)

    for fp, (comment_id, body, resolved) in existing.items():
        if fp not in current and not resolved:
            try:
                client.update_review_comment(comment_id, render_resolved(body, fp))
                report.resolved += 1
            except GitHubError as exc:
                report.errors.append(str(exc))

    if not new:
        return
    payloads = [_comment_payload(f) for f in new]
    try:
        client.create_review(number, head_sha, payloads)
        report.posted += len(payloads)
        return
    except GitHubError as exc:
        # Tek bir geçersiz satır tüm review'u reddettirir; yorumları tek tek dene.
        log.warning("toplu review başarısız, yorumlar tek tek deneniyor: %s", exc)
    for payload in payloads:
        single = {k: v for k, v in payload.items() if k not in {"start_line", "start_side"}}
        try:
            client.create_review_comment(number, head_sha, single)
            report.posted += 1
        except GitHubError as exc:
            report.errors.append(str(exc))


def check_conclusion(result: ReviewResult) -> str:
    """Aegis PR'ı asla bloklamaz: kendi hatasında `neutral`, aksi halde `success`."""
    return "neutral" if result.neutral else "success"


def publish(
    client: GitHubClient, number: int, head_sha: str, result: ReviewResult
) -> PublishReport:
    report = PublishReport()
    try:
        report.summary_comment = upsert_summary(client, number, render_summary(result))
    except GitHubError as exc:
        report.errors.append(str(exc))
    try:
        publish_findings(client, number, head_sha, result.findings, report)
    except GitHubError as exc:
        report.errors.append(str(exc))

    conclusion = check_conclusion(result)
    title = (
        "Aegis incelemeyi tamamlayamadı (PR bloklanmadı)"
        if result.neutral
        else f"{len(result.findings)} bulgu"
    )
    try:
        client.create_check_run(
            head_sha,
            name=CHECK_NAME,
            conclusion=conclusion,
            title=title,
            summary=render_summary(result),
        )
        report.check_conclusion = conclusion
    except GitHubError as exc:
        report.errors.append(str(exc))

    for error in report.errors:
        log.warning("GitHub yayını kısmen başarısız: %s", error)
    return report
