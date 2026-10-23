"""PR yorumlarının Markdown biçimi (docs/architecture.md §6)."""

import hashlib
import re

from aegis.models import Finding
from aegis.review import ReviewResult, ReviewStatus

SUMMARY_MARKER = "<!-- aegis:summary -->"
_FINDING_MARKER = re.compile(r"<!-- aegis:finding:([0-9a-f]{12})(:resolved)? -->")

BAND_TR = {"low": "düşük", "medium": "orta", "high": "yüksek"}

_STATUS_NOTE = {
    ReviewStatus.SKIPPED_LOW_RISK: "Risk düşük olduğu için LLM analizi yapılmadı.",
    ReviewStatus.SKIPPED_NO_LLM: (
        "LLM analizi kapalı (Ollama yapılandırılmadı veya `llm_enabled = false`); "
        "yalnızca gatekeeper ve deterministik kurallar çalıştı."
    ),
}


def _num(n: int) -> str:
    """Türkçe binlik ayracı: 4120 → 4.120"""
    return f"{n:,}".replace(",", ".")


def fingerprint(f: Finding) -> str:
    """Satır kaymalarından etkilenmeyen bulgu kimliği: dosya + kategori + kanıt."""
    evidence = " ".join(f.evidence.split())
    key = f"{f.file}\0{f.category}\0{evidence}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def finding_marker(fp: str, *, resolved: bool = False) -> str:
    return f"<!-- aegis:finding:{fp}{':resolved' if resolved else ''} -->"


def parse_finding_marker(body: str) -> tuple[str, bool] | None:
    """Yorum gövdesindeki işaretten `(parmak izi, çözüldü mü)` döndürür."""
    match = _FINDING_MARKER.search(body)
    return (match.group(1), match.group(2) is not None) if match else None


def render_finding(f: Finding) -> str:
    lines = [
        f"**[{f.category} · {f.severity} · {f.confidence:.2f}]** {f.title}",
        "",
        f.explanation,
    ]
    if f.memory_refs:
        lines += ["", f"Hafıza: {', '.join(f'`{ref}`' for ref in f.memory_refs)}"]
    lines += ["", finding_marker(fingerprint(f))]
    return "\n".join(lines)


def render_resolved(previous_body: str, fp: str) -> str:
    content = _FINDING_MARKER.sub("", previous_body).strip()
    return "\n".join(
        [
            "✅ **Çözüldü** — bu bulgu son incelemede artık görülmüyor.",
            "",
            "<details><summary>Önceki bulgu</summary>",
            "",
            content,
            "",
            "</details>",
            "",
            finding_marker(fp, resolved=True),
        ]
    )


def render_summary(result: ReviewResult) -> str:
    lines = [SUMMARY_MARKER]
    if result.risk is not None:
        band = BAND_TR.get(result.risk.band, result.risk.band)
        lines.append(f"**🛡️ Aegis — Risk: {result.risk.score:.2f} ({band})**")
        if result.risk.reasons:
            lines.append(f"Neden: {' · '.join(result.risk.reasons)}")
    else:
        lines.append("**🛡️ Aegis**")

    if result.neutral:
        lines += [
            "",
            "> [!WARNING]",
            "> Aegis bu incelemeyi tamamlayamadı; PR **bloklanmadı** (fail-open).",
            f"> Neden: `{result.error or 'bilinmeyen hata'}`",
        ]
    elif note := _STATUS_NOTE.get(result.status):
        lines += ["", note]

    if result.summary:
        lines += ["", result.summary]

    outcome = [f"{len(result.findings)} bulgu"]
    if result.usage.input_tokens or result.usage.output_tokens:
        tokens = result.usage.input_tokens + result.usage.output_tokens
        outcome.append(f"{_num(tokens)} token" + (" (cache)" if result.cached else ""))
    lines += ["", f"Sonuç: {' · '.join(outcome)}"]

    if result.metadata_warnings:
        lines += [
            "",
            "⚠️ PR başlığı/açıklaması veya commit mesajlarında incelemeyi "
            "yönlendirmeye çalışan ifadeler var:",
        ]
        lines += [f"- `{w[:200]}`" for w in result.metadata_warnings]

    details = []
    if result.skipped_files:
        details.append(f"Elenen dosyalar: {', '.join(result.skipped_files)}")
    if result.omitted_files:
        details.append(f"Boyut sınırı nedeniyle incelenmeyen: {', '.join(result.omitted_files)}")
    if result.dropped:
        details.append(f"Doğrulamadan geçemeyip düşürülen bulgu: {len(result.dropped)}")
    if result.provider:
        details.append(
            f"Model: `{result.provider}/{result.model}` · prompt `{result.prompt_version}`"
        )
    details.append(f"Süre: {result.duration_seconds:.1f} sn · çalıştırma `{result.run_id}`")
    lines += ["", "<details><summary>Ayrıntılar</summary>", ""]
    lines += [f"- {d}" for d in details]
    lines += ["", "</details>"]
    return "\n".join(lines)
