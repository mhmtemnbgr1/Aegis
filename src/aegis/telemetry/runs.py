"""Çalıştırma metrikleri: her inceleme JSONL dosyasına bir satır ekler (FR-45).

Faz 6'daki dogfooding ve maliyet analizleri bu kayıtlardan üretilir. Kod veya bulgu metni
yazılmaz; yalnızca sayısal/özet alanlar tutulur.
"""

import json
from pathlib import Path
from typing import Any

from aegis.review import ReviewResult


def run_record(result: ReviewResult, **extra: Any) -> dict[str, Any]:
    risk = result.risk
    return {
        "run_id": result.run_id,
        "started_at": result.started_at.isoformat(),
        "duration_seconds": result.duration_seconds,
        "aegis_version": result.aegis_version,
        "status": result.status.value,
        "error": result.error,
        "risk_score": risk.score if risk else None,
        "risk_band": risk.band.value if risk else None,
        "changed_lines": risk.features.get("changed_lines") if risk else None,
        "files_reviewed": result.files_reviewed,
        "files_skipped": len(result.skipped_files),
        "files_omitted": len(result.omitted_files),
        "findings": len(result.findings),
        "findings_dropped": len(result.dropped),
        "metadata_warnings": len(result.metadata_warnings),
        "provider": result.provider,
        "model": result.model,
        "prompt_version": result.prompt_version,
        "llm_calls": result.llm_calls,
        "cached": result.cached,
        "input_tokens": result.usage.input_tokens,
        "output_tokens": result.usage.output_tokens,
        **extra,
    }


def append_run(path: Path | str, result: ReviewResult, **extra: Any) -> None:
    """Kaydı ekler; yazılamazsa sessizce geçer (telemetri incelemeyi bozmamalı)."""
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(run_record(result, **extra), ensure_ascii=False) + "\n")
    except OSError:
        pass
