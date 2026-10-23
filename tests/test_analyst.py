import json
import re
from datetime import UTC, datetime

import pytest
from tenacity import wait_none

from aegis.agents.analyst import Analyst, render_diff, render_file
from aegis.agents.prompts import load_prompts
from aegis.diff import parse_diff
from aegis.gatekeeper import HeuristicGatekeeper
from aegis.llm import MockProvider, StructuredLLM
from aegis.models import AnalysisOutput

DIFF = parse_diff("""\
diff --git a/app/db/pool.py b/app/db/pool.py
index 1111111..2222222 100644
--- a/app/db/pool.py
+++ b/app/db/pool.py
@@ -40,3 +40,4 @@ class ConnectionPool:
     def release(self, conn):
-        self.free.append(conn)
+        if conn.closed:
+            return
         self.size -= 1
""")
RISK = HeuristicGatekeeper().assess(DIFF, as_of=datetime(2026, 10, 23, tzinfo=UTC))


def _analyst(responses: list[object], **kwargs: object) -> tuple[Analyst, MockProvider]:
    provider = MockProvider(responses)  # type: ignore[arg-type]
    return Analyst(StructuredLLM(provider, wait=wait_none()), **kwargs), provider  # type: ignore[arg-type]


def test_load_prompts_v1() -> None:
    prompts = load_prompts("v1")
    assert prompts.version == "v1"
    assert "Do NOT report" in prompts.system
    assert "{diff}" in prompts.user
    with pytest.raises(ValueError):
        load_prompts("v999")


def test_few_shot_examples_match_schema() -> None:
    outputs = re.findall(r"^Output:\n(\{.*\})$", load_prompts().examples, re.MULTILINE)
    assert len(outputs) == 2
    parsed = [AnalysisOutput.model_validate_json(o) for o in outputs]
    assert len(parsed[0].findings) == 1
    assert parsed[1].findings == []  # "bulgu yok" örneği


def test_render_file_uses_new_line_numbers() -> None:
    [f] = DIFF.files
    lines = render_file(f).splitlines()
    assert lines[0] == "### app/db/pool.py (modified)"
    assert lines[1] == "@@ -40,3 +40,4 @@ class ConnectionPool:"
    assert lines[2] == "   40      def release(self, conn):"
    assert lines[3] == "      -        self.free.append(conn)"
    assert lines[4] == "   41 +        if conn.closed:"


def test_render_diff_size_limit() -> None:
    text, omitted = render_diff(DIFF, max_chars=10)
    assert text == ""
    assert omitted == ["app/db/pool.py"]


def test_analyze_with_mock() -> None:
    answer = {
        "summary": "Bir sızıntı var.",
        "findings": [
            {
                "file": "app/db/pool.py",
                "line": 41,
                "category": "resource-leak",
                "severity": "high",
                "confidence": 0.8,
                "title": "size azaltılmıyor",
                "explanation": "erken dönüş",
                "evidence": "if conn.closed:",
            }
        ],
    }
    analyst, provider = _analyst([answer])
    result = analyst.analyze(DIFF, RISK)
    assert result.output is not None
    assert result.output.findings[0].line == 41
    assert result.prompt_version == "v1"
    request = provider.requests[0]
    assert request.system == load_prompts().system
    assert "<pr_diff>\n### app/db/pool.py" in request.prompt
    assert f"Gatekeeper risk: {RISK.score:.2f} ({RISK.band})" in request.prompt
    assert "Write `summary`, `title` and `explanation` in Turkish" in request.prompt
    assert request.json_schema == AnalysisOutput.model_json_schema()


def test_analyze_reports_omitted_files() -> None:
    analyst, provider = _analyst([{"summary": "ok", "findings": []}], max_diff_chars=10)
    result = analyst.analyze(DIFF, RISK)
    assert result.omitted_files == ["app/db/pool.py"]
    assert "Not reviewed (size limit): app/db/pool.py" in provider.requests[0].prompt


def test_analyze_fail_open() -> None:
    analyst, _ = _analyst([])
    result = analyst.analyze(DIFF, RISK)
    assert result.output is None
    assert result.error is not None


def test_prompt_template_survives_braces_in_diff() -> None:
    diff = parse_diff(
        "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -0,0 +1 @@\n+x = {'k': '{diff}'}\n"
    )
    analyst, provider = _analyst([{"summary": "ok", "findings": []}])
    analyst.analyze(diff, RISK)
    assert "x = {'k': '{diff}'}" in provider.requests[0].prompt
    json.dumps(provider.requests[0].model_dump())
