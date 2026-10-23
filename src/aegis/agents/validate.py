"""Halüsinasyon filtreleri (FR-31): kanıtı diff'te olmayan veya değişen satırlara denk gelmeyen
bulgular düşürülür. Tamamen deterministiktir; LLM çıktısına güvenmeden önce uygulanır.
"""

import logging
from enum import StrEnum

from pydantic import BaseModel, Field

from aegis.diff.models import Diff, FileDiff
from aegis.models import Finding

log = logging.getLogger(__name__)

MIN_EVIDENCE_CHARS = 4
"""Bundan kısa kanıtlar (ör. `x`, `)`) her diff'te bulunacağı için kabul edilmez."""


class DropReason(StrEnum):
    UNKNOWN_FILE = "unknown-file"
    INVALID_RANGE = "invalid-range"
    LINE_NOT_CHANGED = "line-not-changed"
    EVIDENCE_TOO_SHORT = "evidence-too-short"
    EVIDENCE_NOT_IN_DIFF = "evidence-not-in-diff"


class DroppedFinding(BaseModel):
    finding: Finding
    reason: DropReason


class ValidationReport(BaseModel):
    kept: list[Finding] = Field(default_factory=list)
    dropped: list[DroppedFinding] = Field(default_factory=list)


def _evidence_lines(evidence: str) -> list[str]:
    """Kanıtı satırlara böler; modelin eklediği diff işaretlerini (`+`, `-`) atar."""
    lines = []
    for raw in evidence.splitlines():
        line = raw.strip()
        if line[:1] in {"+", "-"} and not line.startswith(("++", "--")):
            line = line[1:].strip()
        if line:
            lines.append(line)
    return lines


def evidence_in_diff(evidence: str, f: FileDiff) -> bool:
    """Kanıtın her satırı dosyanın diff satırlarından birinde birebir geçiyor mu?"""
    diff_lines = [line.content.strip() for h in f.hunks for line in h.lines]
    wanted = _evidence_lines(evidence)
    return bool(wanted) and all(any(w in d for d in diff_lines) for w in wanted)


def check_finding(finding: Finding, diff: Diff, line_tolerance: int = 0) -> DropReason | None:
    """Bulgu geçerliyse `None`, değilse düşürülme nedeni."""
    f = diff.get(finding.file)
    if f is None:
        return DropReason.UNKNOWN_FILE
    if finding.last_line < finding.line:
        return DropReason.INVALID_RANGE
    lo, hi = finding.line - line_tolerance, finding.last_line + line_tolerance
    if not any(lo <= n <= hi for n in f.changed_new_lines):
        return DropReason.LINE_NOT_CHANGED
    if len("".join(_evidence_lines(finding.evidence))) < MIN_EVIDENCE_CHARS:
        return DropReason.EVIDENCE_TOO_SHORT
    if not evidence_in_diff(finding.evidence, f):
        return DropReason.EVIDENCE_NOT_IN_DIFF
    return None


def validate_findings(
    findings: list[Finding], diff: Diff, line_tolerance: int = 0
) -> ValidationReport:
    report = ValidationReport()
    for finding in findings:
        reason = check_finding(finding, diff, line_tolerance)
        if reason is None:
            report.kept.append(finding)
        else:
            report.dropped.append(DroppedFinding(finding=finding, reason=reason))
    if report.dropped:
        log.info(
            "%d/%d bulgu düşürüldü: %s",
            len(report.dropped),
            len(findings),
            ", ".join(f"{d.finding.file}:{d.finding.line} ({d.reason})" for d in report.dropped),
        )
    return report
