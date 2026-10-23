"""Ajanlar arasında paylaşılan modeller. Şema: docs/architecture.md §5."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Category(StrEnum):
    BUG = "bug"
    SECURITY = "security"
    CONCURRENCY = "concurrency"
    RESOURCE_LEAK = "resource-leak"
    ERROR_HANDLING = "error-handling"
    API_MISUSE = "api-misuse"
    REGRESSION = "regression"
    PERFORMANCE = "performance"


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file: str
    line: int = Field(ge=1)
    end_line: int | None = Field(default=None, ge=1)
    category: Category
    severity: Severity
    confidence: float = Field(ge=0, le=1)
    title: str = Field(max_length=120)
    explanation: str
    evidence: str
    """Bulgunun dayandığı diff satırının birebir alıntısı."""
    memory_refs: list[str] = Field(default_factory=list)

    @property
    def last_line(self) -> int:
        return self.end_line if self.end_line is not None else self.line


class AnalysisOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(max_length=400)
    findings: list[Finding] = Field(default_factory=list)
