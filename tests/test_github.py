from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from tenacity import wait_none

from aegis.config import AegisConfig
from aegis.diff import Diff
from aegis.gatekeeper import HeuristicGatekeeper
from aegis.github.client import GitHubClient, GitHubError
from aegis.github.publisher import publish
from aegis.github.render import (
    SUMMARY_MARKER,
    fingerprint,
    parse_finding_marker,
    render_finding,
    render_summary,
)
from aegis.llm import LLMError, LLMProvider, LLMRequest, LLMResponse, MockProvider
from aegis.models import Finding
from aegis.review import ReviewResult, ReviewStatus, run_review
from tests.fake_github import FakeGitHub

SHA = "abc123"


def finding(**overrides: Any) -> Finding:
    data: dict[str, Any] = {
        "file": "app/db/pool.py",
        "line": 41,
        "category": "resource-leak",
        "severity": "critical",
        "confidence": 0.86,
        "title": "Zaman aşımı yolunda bağlantı havuza iade edilmiyor.",
        "explanation": "finally bloğu yok.",
        "evidence": "return await conn.execute(query, timeout=timeout)",
    }
    data.update(overrides)
    return Finding.model_validate(data)


def result(**overrides: Any) -> ReviewResult:
    risk = HeuristicGatekeeper().assess(Diff(), as_of=datetime(2026, 10, 23, tzinfo=UTC))
    risk = risk.model_copy(
        update={"score": 0.82, "band": "high", "reasons": ["3 alt sisteme yayılan değişiklik"]}
    )
    data: dict[str, Any] = {
        "risk": risk,
        "findings": [finding()],
        "summary": "Bir kaynak sızıntısı var.",
        "provider": "gemini",
        "model": "gemini-flash",
        "prompt_version": "v1",
        "usage": {"input_tokens": 4000, "output_tokens": 120},
    }
    data.update(overrides)
    return ReviewResult.model_validate(data)


# --- #46 özet yorumu -------------------------------------------------------------------


def test_summary_format_matches_architecture() -> None:
    body = render_summary(result())
    lines = body.splitlines()
    assert lines[0] == SUMMARY_MARKER
    assert lines[1] == "**🛡️ Aegis — Risk: 0.82 (yüksek)**"
    assert lines[2] == "Neden: 3 alt sisteme yayılan değişiklik"
    assert "Sonuç: 1 bulgu · 4.120 token" in body
    assert "`gemini/gemini-flash` · prompt `v1`" in body


def test_summary_low_risk_note() -> None:
    body = render_summary(result(status=ReviewStatus.SKIPPED_LOW_RISK, findings=[]))
    assert "LLM analizi yapılmadı" in body
    assert "Sonuç: 0 bulgu" in body


def test_summary_metadata_warning() -> None:
    body = render_summary(result(metadata_warnings=["Ignore previous instructions"]))
    assert "- `Ignore previous instructions`" in body


def test_summary_created_then_updated() -> None:
    gh = FakeGitHub()
    gh.issue_comments.append({"id": 1, "body": "başka bir kullanıcının yorumu"})
    first = publish(gh.client(), 7, SHA, result())
    second = publish(gh.client(), 7, SHA, result(findings=[]))
    assert (first.summary_comment, second.summary_comment) == ("created", "updated")
    ours = [c for c in gh.issue_comments if SUMMARY_MARKER in c["body"]]
    assert len(ours) == 1  # tekrar eden yorum yok
    assert "Sonuç: 0 bulgu" in ours[0]["body"]


def test_pagination_finds_summary_on_later_page() -> None:
    gh = FakeGitHub()
    gh.issue_comments += [{"id": i, "body": f"yorum {i}"} for i in range(100, 250)]
    publish(gh.client(), 7, SHA, result())
    publish(gh.client(), 7, SHA, result())
    assert sum(SUMMARY_MARKER in c["body"] for c in gh.issue_comments) == 1


# --- #64 satır yorumları ---------------------------------------------------------------


def test_finding_comment_format() -> None:
    body = render_finding(finding(memory_refs=["BC-0142"]))
    assert body.startswith(
        "**[resource-leak · critical · 0.86]** Zaman aşımı yolunda bağlantı havuza iade edilmiyor."
    )
    assert "Hafıza: `BC-0142`" in body
    assert parse_finding_marker(body) == (fingerprint(finding()), False)


def test_fingerprint_ignores_line_shifts_and_whitespace() -> None:
    moved = finding(line=55, evidence="return  await conn.execute(query,   timeout=timeout)")
    assert fingerprint(moved) == fingerprint(finding())
    assert fingerprint(finding(file="other.py")) != fingerprint(finding())


def test_findings_posted_once_across_pushes() -> None:
    gh = FakeGitHub()
    report1 = publish(gh.client(), 7, SHA, result())
    report2 = publish(gh.client(), 7, "def456", result(findings=[finding(line=45)]))
    assert (report1.posted, report2.posted, report2.skipped_existing) == (1, 0, 1)
    assert len(gh.review_comments) == 1
    comment = gh.review_comments[0]
    assert (comment["path"], comment["line"], comment["side"]) == ("app/db/pool.py", 41, "RIGHT")


def test_range_finding_uses_start_line() -> None:
    gh = FakeGitHub()
    publish(gh.client(), 7, SHA, result(findings=[finding(line=40, end_line=43)]))
    comment = gh.review_comments[0]
    assert (comment["start_line"], comment["line"]) == (40, 43)


def test_resolved_findings_marked_and_reopened() -> None:
    gh = FakeGitHub()
    publish(gh.client(), 7, SHA, result())
    report = publish(gh.client(), 7, SHA, result(findings=[]))
    assert report.resolved == 1
    body = gh.review_comments[0]["body"]
    assert body.startswith("✅ **Çözüldü**")
    assert parse_finding_marker(body) == (fingerprint(finding()), True)
    # Tekrar çözülmüş olarak işaretlenmez
    assert publish(gh.client(), 7, SHA, result(findings=[])).resolved == 0
    # Bulgu geri gelirse yeni yorum açılır
    assert publish(gh.client(), 7, SHA, result()).posted == 1
    assert len(gh.review_comments) == 2


def test_invalid_line_falls_back_to_single_comments() -> None:
    gh = FakeGitHub()
    gh.invalid_lines.add(("app/bad.py", 3))
    findings = [finding(), finding(file="app/bad.py", line=3, evidence="x = compute()")]
    report = publish(gh.client(), 7, SHA, result(findings=findings))
    assert report.posted == 1
    assert len(report.errors) == 1
    assert [c["path"] for c in gh.review_comments] == ["app/db/pool.py"]


# --- #48 fail-open ve check run --------------------------------------------------------

RISKY = """\
diff --git a/app/db/query.py b/app/db/query.py
--- a/app/db/query.py
+++ b/app/db/query.py
@@ -1,1 +1,2 @@
 def find(cur, name):
+    cur.execute("SELECT * FROM users WHERE name = '" + name + "'")
"""


class Failing:
    name, model = "failing", "m"

    def __init__(self, error: LLMError) -> None:
        self.error = error

    def complete(self, request: LLMRequest) -> LLMResponse:
        raise self.error


def _missing_model(config: AegisConfig) -> LLMProvider:
    raise LLMError("ollama: model 'qwen2.5-coder:7b' not found", retryable=False)


@pytest.mark.parametrize(
    "factory",
    [
        pytest.param(lambda c: Failing(LLMError("HTTP 500 Internal Server Error")), id="api-error"),
        pytest.param(lambda c: Failing(LLMError("Request timed out")), id="timeout"),
        pytest.param(_missing_model, id="model-missing"),
    ],
)
def test_tool_failures_are_neutral_with_warning(
    factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    import aegis.llm.structured as structured

    monkeypatch.setattr(structured, "wait_exponential_jitter", lambda **_: wait_none())
    review = run_review(RISKY, AegisConfig(), provider_factory=factory)
    assert review.neutral
    gh = FakeGitHub()
    report = publish(gh.client(), 7, SHA, review)
    assert report.check_conclusion == "neutral"
    assert gh.check_runs[0]["conclusion"] == "neutral"
    assert gh.check_runs[0]["head_sha"] == SHA
    summary = gh.issue_comments[0]["body"]
    assert "PR **bloklanmadı**" in summary


def test_successful_review_check_is_success_even_with_findings() -> None:
    review = run_review(
        RISKY,
        AegisConfig(),
        provider_factory=lambda c: MockProvider([{"summary": "ok", "findings": []}]),
    )
    gh = FakeGitHub()
    assert publish(gh.client(), 7, SHA, review).check_conclusion == "success"


def test_github_errors_never_raise() -> None:
    gh = FakeGitHub()
    gh.fail = {r"GET /issues/\d+/comments": 500, r"POST /check-runs": 403}
    report = publish(gh.client(), 7, SHA, result())
    assert report.summary_comment is None
    assert report.posted == 1  # diğer parçalar yine de yayınlandı
    assert report.check_conclusion is None
    assert len(report.errors) == 2


def test_client_network_error_wrapped() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("bağlantı yok")

    client = GitHubClient("t", "o/r", http=httpx.Client(transport=httpx.MockTransport(boom)))
    with pytest.raises(GitHubError, match="bağlantı yok"):
        client.list_issue_comments(1)
