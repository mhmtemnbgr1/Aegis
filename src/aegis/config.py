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
        r"\bsubprocess\.",
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


class AegisConfig(_Section):
    gatekeeper: GatekeeperConfig = GatekeeperConfig()
    filters: FiltersConfig = FiltersConfig()


def load_config(repo: Path | str = ".") -> AegisConfig:
    """Repo kökündeki `.aegis.toml` dosyasını okur; yoksa varsayılanları döndürür."""
    path = Path(repo) / CONFIG_FILE
    if not path.is_file():
        return AegisConfig()
    with path.open("rb") as fh:
        return AegisConfig.model_validate(tomllib.load(fh))
