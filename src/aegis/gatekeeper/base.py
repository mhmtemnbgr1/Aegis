"""Gatekeeper arayüzü: sezgisel kural ve eğitilmiş model aynı protokolü uygular."""

from datetime import datetime
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, Field

from aegis.diff.models import Diff


class RiskBand(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


def band_for(score: float, low_threshold: float, high_threshold: float) -> RiskBand:
    """`score < low` → düşük, `score >= high` → yüksek, arası orta."""
    if score < low_threshold:
        return RiskBand.LOW
    if score >= high_threshold:
        return RiskBand.HIGH
    return RiskBand.MEDIUM


class RiskAssessment(BaseModel):
    score: float = Field(ge=0, le=1)
    band: RiskBand
    reasons: list[str] = Field(default_factory=list)
    """PR yorumunda gösterilecek, insan okunur gerekçeler."""
    features: dict[str, float] = Field(default_factory=dict)
    """Skoru oluşturan ham değerler (deneyler ve açıklama için)."""


class Gatekeeper(Protocol):
    def assess(self, diff: Diff, *, as_of: datetime) -> RiskAssessment:
        """Ön filtreden geçmiş diff için risk skoru üretir.

        `as_of`, değerlendirilen PR/commit'in tarihidir; geçmişe dayalı uygulamalar
        yalnızca bu tarihte bilinen veriyi kullanmalıdır (FR-18).
        """
        ...
