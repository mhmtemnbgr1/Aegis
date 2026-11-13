"""Çevrimiçi hat (Faz 1 iskeleti): diff → ön filtre → gatekeeper → analiz → filtreler.

`run_review` hiçbir zaman exception fırlatmaz (fail-open, NFR-01): hata durumunda sonuç
`status=error` ile döner ve çağıran taraf PR'ı bloklamadan uyarı yayınlar.
"""

import logging
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum

from pathspec import GitIgnoreSpec
from pydantic import BaseModel, Field

from aegis import __version__
from aegis.agents.analyst import Analyst
from aegis.agents.injection import detect_injections, merge_findings, scan_text
from aegis.agents.validate import DroppedFinding, validate_findings
from aegis.config import AegisConfig
from aegis.diff import FilterResult, filter_diff, parse_diff
from aegis.gatekeeper import Gatekeeper, HeuristicGatekeeper, RiskAssessment, RiskBand
from aegis.llm import LLMProvider, ResponseCache, StructuredLLM, Usage, create_provider
from aegis.models import Finding

log = logging.getLogger(__name__)

ANALYST = "analyst"


class ReviewStatus(StrEnum):
    OK = "ok"
    """Analiz yapıldı."""
    SKIPPED_LOW_RISK = "skipped-low-risk"
    """Risk düşük; LLM çağrılmadı."""
    SKIPPED_NO_LLM = "skipped-no-llm"
    """LLM devre dışı (ör. fork PR'ında bulut sağlayıcısı)."""
    LLM_ERROR = "llm-error"
    """LLM çağrısı başarısız; yalnızca deterministik sonuçlar var."""
    ERROR = "error"
    """Aracın kendi hatası."""


class ReviewResult(BaseModel):
    run_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    duration_seconds: float = 0.0
    aegis_version: str = __version__
    status: ReviewStatus = ReviewStatus.OK
    error: str | None = None
    risk: RiskAssessment | None = None
    files_reviewed: int = 0
    skipped_files: list[str] = Field(default_factory=list)
    omitted_files: list[str] = Field(default_factory=list)
    summary: str | None = None
    findings: list[Finding] = Field(default_factory=list)
    dropped: list[DroppedFinding] = Field(default_factory=list)
    metadata_warnings: list[str] = Field(default_factory=list)
    """PR başlığı/açıklaması/commit mesajlarında görülen injection kalıpları."""
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    llm_calls: int = 0
    cached: bool = False
    usage: Usage = Usage()

    @property
    def neutral(self) -> bool:
        """Check run `neutral` sonuçlanmalı mı (aracın kendi hatası)?"""
        return self.status in {ReviewStatus.ERROR, ReviewStatus.LLM_ERROR}


ProviderFactory = Callable[[AegisConfig], LLMProvider]


def _default_provider(config: AegisConfig) -> LLMProvider:
    return create_provider(config.agent(ANALYST))


def run_review(
    diff_text: str,
    config: AegisConfig,
    *,
    ignore: GitIgnoreSpec | None = None,
    metadata: str | None = None,
    as_of: datetime | None = None,
    llm_enabled: bool = True,
    provider_factory: ProviderFactory = _default_provider,
    cache: ResponseCache | None = None,
    gatekeeper: Gatekeeper | None = None,
) -> ReviewResult:
    """`gatekeeper` verilmezse sezgisel kural kullanılır (bkz. `gatekeeper.factory`)."""
    result = ReviewResult()
    start = time.perf_counter()
    try:
        _run(
            result,
            diff_text,
            config,
            ignore=ignore,
            metadata=metadata,
            as_of=as_of or result.started_at,
            llm_enabled=llm_enabled,
            provider_factory=provider_factory,
            cache=cache,
            gatekeeper=gatekeeper or HeuristicGatekeeper(config.gatekeeper),
        )
    except Exception as exc:  # fail-open: hiçbir hata PR'ı bloklamaz
        log.exception("inceleme başarısız")
        result.status = ReviewStatus.ERROR
        result.error = f"{type(exc).__name__}: {exc}"
    result.duration_seconds = round(time.perf_counter() - start, 3)
    return result


def _run(
    result: ReviewResult,
    diff_text: str,
    config: AegisConfig,
    *,
    ignore: GitIgnoreSpec | None,
    metadata: str | None,
    as_of: datetime,
    llm_enabled: bool,
    provider_factory: ProviderFactory,
    cache: ResponseCache | None,
    gatekeeper: Gatekeeper,
) -> None:
    filtered: FilterResult = filter_diff(
        parse_diff(diff_text),
        ignore=ignore,
        max_changed_lines=config.filters.max_changed_lines_per_file,
    )
    diff = filtered.diff
    result.files_reviewed = len(diff.files)
    result.skipped_files = [f"{s.path} ({s.reason})" for s in filtered.skipped]
    result.metadata_warnings = scan_text(metadata or "")

    risk = gatekeeper.assess(diff, as_of=as_of)
    result.risk = risk
    detected = detect_injections(diff, GitIgnoreSpec.from_lines(config.review.injection_exclude))
    model_findings: list[Finding] = []

    if risk.band is RiskBand.LOW:
        result.status = ReviewStatus.SKIPPED_LOW_RISK
    elif not llm_enabled:
        result.status = ReviewStatus.SKIPPED_NO_LLM
    else:
        provider = provider_factory(config)
        result.provider, result.model = provider.name, provider.model
        analyst = Analyst(
            StructuredLLM(provider, cache=cache),
            prompt_version=config.review.prompt_version,
            language=config.review.language,
        )
        analysis = analyst.analyze(diff, risk, metadata)
        result.prompt_version = analysis.prompt_version
        result.omitted_files = analysis.omitted_files
        result.llm_calls, result.cached, result.usage = (
            analysis.calls,
            analysis.cached,
            analysis.usage,
        )
        if analysis.output is None:
            result.status = ReviewStatus.LLM_ERROR
            result.error = analysis.error
        else:
            result.summary = analysis.output.summary
            model_findings = analysis.output.findings

    report = validate_findings(merge_findings(model_findings, detected), diff)
    result.findings, result.dropped = report.kept, report.dropped
