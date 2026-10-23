import logging
from typing import Any

import pytest
from pydantic import ValidationError

from aegis.agents.validate import DropReason, check_finding, evidence_in_diff, validate_findings
from aegis.diff import parse_diff
from aegis.models import AnalysisOutput, Finding

DIFF = parse_diff("""\
diff --git a/app/db/pool.py b/app/db/pool.py
index 1111111..2222222 100644
--- a/app/db/pool.py
+++ b/app/db/pool.py
@@ -40,4 +40,6 @@ class ConnectionPool:
     def release(self, conn):
-        self.free.append(conn)
+        if conn.closed:
+            return
+        self.free.append(conn)
         self.size -= 1
         return None
diff --git a/app/old.py b/app/old.py
deleted file mode 100644
index 3333333..0000000
--- a/app/old.py
+++ /dev/null
@@ -1 +0,0 @@
-import pickle
""")


def finding(**overrides: Any) -> Finding:
    data: dict[str, Any] = {
        "file": "app/db/pool.py",
        "line": 41,
        "category": "resource-leak",
        "severity": "high",
        "confidence": 0.8,
        "title": "Kapalı bağlantı havuzdan düşülmüyor",
        "explanation": "size azaltılmadan dönülüyor.",
        "evidence": "if conn.closed:",
    }
    data.update(overrides)
    return Finding.model_validate(data)


def test_valid_finding_kept() -> None:
    assert check_finding(finding(), DIFF) is None


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        # Var olmayan dosya
        ({"file": "app/db/connection.py"}, DropReason.UNKNOWN_FILE),
        # Bağlam satırı (değişmemiş): def release
        ({"line": 40, "evidence": "def release(self, conn):"}, DropReason.LINE_NOT_CHANGED),
        # Hunk dışında bir satır
        ({"line": 120}, DropReason.LINE_NOT_CHANGED),
        # Silinen dosyada yeni tarafta satır yok
        (
            {"file": "app/old.py", "line": 1, "evidence": "import pickle"},
            DropReason.LINE_NOT_CHANGED,
        ),
        # Ters aralık
        ({"line": 43, "end_line": 41}, DropReason.INVALID_RANGE),
        # Uydurulmuş kanıt
        ({"evidence": "conn.close()"}, DropReason.EVIDENCE_NOT_IN_DIFF),
        # Kanıtın bir satırı uydurma
        ({"evidence": "if conn.closed:\n    pool.leak()"}, DropReason.EVIDENCE_NOT_IN_DIFF),
        # Anlamsız kısa kanıt
        ({"evidence": "if"}, DropReason.EVIDENCE_TOO_SHORT),
        ({"evidence": "  \n + "}, DropReason.EVIDENCE_TOO_SHORT),
    ],
)
def test_hallucinations_dropped(overrides: dict[str, Any], reason: DropReason) -> None:
    assert check_finding(finding(**overrides), DIFF) is reason


@pytest.mark.parametrize(
    "evidence",
    [
        "if conn.closed:",
        "+        if conn.closed:",  # model diff işaretini de alıntılamış
        "if conn.closed:\n    return",  # çok satırlı
        "self.free.append(conn)",  # silinen satırda da geçiyor
        "conn.closed",  # satırın bir parçası
    ],
)
def test_evidence_variants_accepted(evidence: str) -> None:
    f = DIFF.get("app/db/pool.py")
    assert f is not None
    assert evidence_in_diff(evidence, f)


def test_range_overlapping_changed_line_kept() -> None:
    # 40 bağlam, 41 eklenen: aralık değişen satıra değiyor
    assert check_finding(finding(line=40, end_line=41), DIFF) is None


def test_line_tolerance() -> None:
    off_by_one = finding(line=40, evidence="if conn.closed:")
    assert check_finding(off_by_one, DIFF) is DropReason.LINE_NOT_CHANGED
    assert check_finding(off_by_one, DIFF, line_tolerance=1) is None


def test_validate_findings_report_and_log(caplog: pytest.LogCaptureFixture) -> None:
    findings = [finding(), finding(evidence="uydurma kod"), finding(file="yok.py")]
    with caplog.at_level(logging.INFO, logger="aegis.agents.validate"):
        report = validate_findings(findings, DIFF)
    assert report.kept == [findings[0]]
    assert [d.reason for d in report.dropped] == [
        DropReason.EVIDENCE_NOT_IN_DIFF,
        DropReason.UNKNOWN_FILE,
    ]
    assert "2/3 bulgu düşürüldü" in caplog.text


def test_analysis_output_schema() -> None:
    out = AnalysisOutput.model_validate({"summary": "Sorun yok.", "findings": []})
    assert out.findings == []
    schema = AnalysisOutput.model_json_schema()
    assert schema["required"] == ["summary"]
    assert schema["additionalProperties"] is False
    with pytest.raises(ValidationError):
        finding(severity="blocker")
    with pytest.raises(ValidationError):
        finding(confidence=1.5)
    with pytest.raises(ValidationError):
        AnalysisOutput.model_validate({"summary": "x" * 401})
