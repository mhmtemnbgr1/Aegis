"""Prompt injection önlemleri (NFR-08, docs/architecture.md §7).

1. PR içeriği prompt'ta `<pr_diff>` / `<pr_metadata>` ayraçları arasında veri olarak verilir;
   içerikteki sahte ayraçlar etkisizleştirilir.
2. Bilinen saldırı kalıpları deterministik olarak taranır. Eklenen satırlardaki eşleşmeler,
   modelin ne döndürdüğünden bağımsız olarak `security` bulgusu olur; böylece modeli
   "bulgu raporlama" diye kandırmak bulguyu bastıramaz.
3. Ajanın araç yetkisi yoktur ve çıktı şeması fazladan alan kabul etmez (`extra="forbid"`).
"""

import re

from pathspec import GitIgnoreSpec

from aegis.diff.models import Diff
from aegis.gatekeeper.heuristic import is_test_file
from aegis.models import Category, Finding, Severity

_DELIMITER = re.compile(r"<(/?)\s*(pr_diff|pr_metadata)\b", re.IGNORECASE)

INJECTION_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\b(ignore|disregard|forget)\b.{0,30}\b(previous|prior|above|all|earlier)\b.{0,20}"
        r"\b(instructions?|rules|prompts?)\b",
        r"\byou are now\b",
        r"\b(new|updated|override) (system )?instructions?\b",
        # Çıplak "system prompt" ifadesi (ör. bir commit mesajında) talimat değildir.
        r"\b(ignore|reveal|print|show|override|replace|new)\b.{0,20}\bsystem prompt\b",
        r"\b(do not|don't|never) (report|flag|mention)\b",
        r"\breport (no|zero) (findings|issues|bugs)\b",
        r"\b(approve|lgtm)\b.{0,20}\b(this|the) (pr|pull request|change)\b",
        r"\bthis (code|change|function|pr) is (safe|secure|correct)\b",
        r"\b(suggest|apply|use) (the following|this) patch\b",
        r"\bAI (reviewer|assistant|model)\b",
        r"</?\s*(pr_diff|pr_metadata)\b",
        # Türkçe kalıplar
        r"\b(önceki|yukarıdaki|tüm)\b.{0,20}\btalimat\w*\b.{0,20}\b(yok say|unut|görmezden gel)",
        r"\bbulgu\w* (raporlama|bildirme|yazma)\b",
        r"\bbu (kod|değişiklik|fonksiyon) güvenli\w*\b",
    )
]

INJECTION_TITLE = "Olası prompt injection girişimi"


def neutralize_delimiters(text: str) -> str:
    """İçerikteki `<pr_diff>` benzeri ayraçları bozar; veri bloğundan çıkılamaz."""
    return _DELIMITER.sub(lambda m: f"&lt;{m.group(1)}{m.group(2)}", text)


def is_injection(text: str) -> bool:
    return any(p.search(text) for p in INJECTION_PATTERNS)


def scan_text(text: str) -> list[str]:
    """Serbest metindeki (PR başlığı, açıklaması, commit mesajları) şüpheli satırlar."""
    return [line.strip() for line in text.splitlines() if is_injection(line)]


def detect_injections(diff: Diff, exclude: GitIgnoreSpec | None = None) -> list[Finding]:
    """Eklenen satırlarda saldırı kalıbı arar; her eşleşme için bir güvenlik bulgusu üretir.

    Test dosyaları ve `exclude` ile eşleşen yollar atlanır (saldırı örnekleri orada meşrudur).
    """
    findings = []
    for f in diff.files:
        if is_test_file(f.path) or (exclude is not None and exclude.match_file(f.path)):
            continue
        for h in f.hunks:
            for line in h.added_lines:
                if line.new_lineno is None or not is_injection(line.content):
                    continue
                findings.append(
                    Finding(
                        file=f.path,
                        line=line.new_lineno,
                        category=Category.SECURITY,
                        severity=Severity.HIGH,
                        confidence=0.9,
                        title=INJECTION_TITLE,
                        explanation=(
                            "Bu satır, otomatik inceleme araçlarını yönlendirmeye çalışan bir "
                            "talimat içeriyor. Kod incelemesi bu metne göre değiştirilmedi; "
                            "satırın amacını bir insan gözden geçirmeli."
                        ),
                        evidence=line.content.strip(),
                    )
                )
    return findings


def merge_findings(model: list[Finding], detected: list[Finding]) -> list[Finding]:
    """Dedektör bulgularını ekler; modelin aynı satır için bulgusu varsa tekrarlamaz."""
    seen = {(f.file, n) for f in model for n in range(f.line, f.last_line + 1)}
    return model + [d for d in detected if (d.file, d.line) not in seen]
