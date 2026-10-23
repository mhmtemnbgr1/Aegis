"""`.aegis.toml` yapılandırması.

Henüz uygulanmamış bölümler (ör. `[agents]`) okunur ama yok sayılır; ilgili fazda modele eklenir.
"""

import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CONFIG_FILE = ".aegis.toml"


class _Section(BaseModel):
    model_config = ConfigDict(extra="ignore")


class HeuristicConfig(_Section):
    """Sezgisel gatekeeper ağırlıkları. Skor, bileşenlerin ağırlıklı ortalamasıdır."""

    size_weight: float = Field(default=0.4, ge=0)
    path_weight: float = Field(default=0.3, ge=0)
    api_weight: float = Field(default=0.3, ge=0)
    size_saturation: int = Field(default=400, gt=0)
    """Bu kadar değişen satırda boyut bileşeni 1'e ulaşır."""
    api_saturation: int = Field(default=2, gt=0)
    """Bu kadar riskli API kullanımında API bileşeni 1'e ulaşır."""
    risky_paths: list[str] = [
        "auth",
        "login",
        "password",
        "secret",
        "token",
        "session",
        "permission",
        "crypto",
        "security",
        "db",
        "database",
        "sql",
        "migration",
        "payment",
        "billing",
    ]
    risky_apis: list[str] = [
        r"\beval\(",
        r"\bexec\(",
        r"\b__import__\(",
        # Yalnızca süreç başlatan çağrılar; `except subprocess.CalledProcessError` riskli değil.
        r"\bsubprocess\.(run|call|check_call|check_output|Popen|getoutput|getstatusoutput)\(",
        r"\bos\.(system|popen)\(",
        r"shell\s*=\s*True",
        r"\bpickle\.loads?\(",
        r"\bmarshal\.loads?\(",
        r"\byaml\.load\(",
        r"verify\s*=\s*False",
        r"\btempfile\.mktemp\(",
        # SQL string birleştirme: execute("..." + x), execute(f"..."), execute("..." % x)
        r"\.(execute|executemany|raw)\(\s*(f[\"']|[\"'][^\"']*[\"']\s*(\+|%|\.format))",
    ]

    @model_validator(mode="after")
    def _some_weight(self) -> "HeuristicConfig":
        if self.size_weight + self.path_weight + self.api_weight <= 0:
            raise ValueError("en az bir ağırlık pozitif olmalı")
        return self


class GatekeeperConfig(_Section):
    mode: Literal["heuristic", "model"] = "heuristic"
    low_threshold: float = Field(default=0.30, ge=0, le=1)
    high_threshold: float = Field(default=0.70, ge=0, le=1)
    heuristic: HeuristicConfig = HeuristicConfig()

    @model_validator(mode="after")
    def _ordered(self) -> "GatekeeperConfig":
        if self.low_threshold > self.high_threshold:
            raise ValueError("low_threshold, high_threshold'dan büyük olamaz")
        return self


class FiltersConfig(_Section):
    max_changed_lines_per_file: int | None = Field(default=1500, gt=0)


class AgentConfig(_Section):
    """Bir ajanın kullanacağı sağlayıcı ve model (FR-37)."""

    provider: Literal["ollama", "gemini", "openai", "anthropic"] = "ollama"
    model: str = "qwen2.5-coder:7b"
    temperature: float | None = Field(default=0.0, ge=0, le=2)
    """Anthropic'te yok sayılır (güncel Claude modelleri desteklemez)."""
    effort: Literal["low", "medium", "high", "xhigh", "max"] | None = None
    """Yalnızca Anthropic: `output_config.effort`."""
    timeout_seconds: float = Field(default=60, gt=0)


class ReviewConfig(_Section):
    llm_enabled: bool = True
    """False ise analiz ajanı hiç çağrılmaz; yalnızca gatekeeper ve deterministik kurallar."""
    language: str = "Turkish"
    """Bulgu başlığı, açıklaması ve özetin yazılacağı dil."""
    prompt_version: str = "v1"
    cache_dir: str = ".aegis/cache/llm"
    runs_path: str = ".aegis/runs.jsonl"
    """Çalıştırma metriklerinin eklendiği JSONL dosyası (FR-45)."""
    injection_exclude: list[str] = []
    """Injection dedektörünün atlayacağı yollar (gitignore sözdizimi), ör. prompt dosyaları.
    LLM incelemesi bu dosyalarda yine yapılır."""


class AegisConfig(_Section):
    gatekeeper: GatekeeperConfig = GatekeeperConfig()
    filters: FiltersConfig = FiltersConfig()
    agents: dict[str, AgentConfig] = {}
    review: ReviewConfig = ReviewConfig()

    def agent(self, name: str) -> AgentConfig:
        """Ajanın ayarı; tanımlı değilse varsayılan (yerel Ollama)."""
        return self.agents.get(name, AgentConfig())


def parse_config(text: str) -> AegisConfig:
    return AegisConfig.model_validate(tomllib.loads(text))


def load_config(repo: Path | str = ".", path: Path | str | None = None) -> AegisConfig:
    """`path` verilmişse onu, yoksa repo kökündeki `.aegis.toml`'u okur; yoksa varsayılanlar."""
    if path is not None:
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(f"yapılandırma dosyası bulunamadı: {path}")
    else:
        path = Path(repo) / CONFIG_FILE
        if not path.is_file():
            return AegisConfig()
    with path.open("rb") as fh:
        return AegisConfig.model_validate(tomllib.load(fh))
