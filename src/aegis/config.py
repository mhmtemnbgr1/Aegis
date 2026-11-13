"""`.aegis.toml` yapılandırması.

Henüz uygulanmamış bölümler (ör. `[agents]`) okunur ama yok sayılır; ilgili fazda modele eklenir.
"""

import re
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CONFIG_FILE = ".aegis.toml"


class _Section(BaseModel):
    model_config = ConfigDict(extra="ignore")


class HeuristicConfig(_Section):
    """Sezgisel gatekeeper ağırlıkları. Skor, bileşenlerin ağırlıklı ortalamasıdır."""

    size_weight: float = Field(default=0.5, ge=0)
    path_weight: float = Field(default=0.5, ge=0)
    size_saturation: int = Field(default=400, gt=0)
    """Bu kadar değişen satırda boyut bileşeni 1'e ulaşır."""
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

    @model_validator(mode="after")
    def _some_weight(self) -> "HeuristicConfig":
        if self.size_weight + self.path_weight <= 0:
            raise ValueError("en az bir ağırlık pozitif olmalı")
        return self


class GatekeeperConfig(_Section):
    mode: Literal["heuristic", "model"] = "heuristic"
    low_threshold: float = Field(default=0.30, ge=0, le=1)
    high_threshold: float = Field(default=0.70, ge=0, le=1)
    max_llm_pr_ratio: float | None = Field(default=None, gt=0, le=1)
    """Verilirse (yalnızca `model` modunda) eşikler bütçeden hesaplanır: PR'ların en fazla bu
    payı orta/yüksek banda düşer ve LLM'e gider (FR-13)."""
    high_share: float = Field(default=0.5, gt=0, le=1)
    """Bütçe modunda LLM'e gidenlerin en riskli bu kadarı yüksek banttır."""
    models_dir: str = ".aegis/models"
    """`model` modunda modellerin arandığı dizin: `<dizin>/<repo>/`, yoksa `<dizin>/all/`."""
    model_name: Literal["lr", "rf", "lightgbm"] = "lr"
    budget_window: int = Field(default=50, gt=0)
    """Bütçe eşiği, model modunda puanlanmış son bu kadar PR'ın skorundan yeniden hesaplanır."""
    budget_min_runs: int = Field(default=20, gt=0)
    """Bu kadar kayıt yoksa eşik modelin doğrulama skorlarından hesaplanır."""
    heuristic: HeuristicConfig = HeuristicConfig()

    @model_validator(mode="after")
    def _ordered(self) -> "GatekeeperConfig":
        if self.low_threshold > self.high_threshold:
            raise ValueError("low_threshold, high_threshold'dan büyük olamaz")
        return self


class MemoryConfig(_Section):
    """Bug-fix hafızası (Katman 2, FR-20…FR-24)."""

    index_path: str = ".aegis/memory"
    embedding_model: str = "lsa"
    """`lsa` (varsayılan, ek bağımlılık yok), `lsa:<boyut>` ya da `ollama:<model>` (#24)."""
    top_k: int = Field(default=3, gt=0)
    retrieval: Literal["hybrid", "vector", "structural", "bm25"] = "hybrid"
    """Getirme modu (#25); `bm25` ablasyon için."""
    max_functions_per_card: int = Field(default=3, gt=0)
    """Bir kartta saklanan en çok fonksiyon (önceki/sonraki kod)."""
    max_code_lines: int = Field(default=60, gt=0)
    """Kartta fonksiyon başına en çok satır; uzun fonksiyonlar kırpılır."""
    max_diff_lines: int = Field(default=120, gt=0)
    """Karttaki fix diff'inin en çok satırı."""


class FiltersConfig(_Section):
    max_changed_lines_per_file: int | None = Field(default=1500, gt=0)


class AgentConfig(_Section):
    """Bir ajanın kullanacağı sağlayıcı ve model (FR-37)."""

    provider: Literal["ollama"] = "ollama"
    model: str = "qwen2.5-coder:7b"
    temperature: float | None = Field(default=0.0, ge=0, le=2)
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


class MiningConfig(_Section):
    """Repo madenciliği ve fix-commit tespiti (FR-01, FR-02)."""

    data_dir: str = ".aegis/data"
    """Madencilik çıktılarının (Parquet) yazıldığı kök dizin; her repo bir alt dizin."""
    clone_dir: str = ".aegis/repos"
    """URL verildiğinde repoların klonlandığı kök dizin."""
    fix_patterns: list[str] = [
        r"\bfix(e[sd]|ing)?\b",
        r"\bbug(s|fix|fixes)?\b",
        r"\bhotfix\b",
        r"\bregressions?\b",
        r"\bleak(s|ing)?\b",
        r"\bcrash(es|ed|ing)?\b",
        r"\bdefects?\b",
    ]
    """Commit mesajında (büyük/küçük harf duyarsız) aranan fix kalıpları (regex)."""
    fix_exclude_patterns: list[str] = [
        r"^revert\b",
        r"\btypos?\b",
        r"\bspelling\b",
        r"\bdocs?\b",
        r"\bdocumentation\b",
        r"\breadme\b",
        r"\bchangelog\b",
        r"\blint(ing)?\b",
        r"\bflake8\b",
        r"\bmypy\b",
        r"\bpep ?8\b",
        r"\bformatting\b",
        r"\bwhitespace\b",
        r"\bci\b",
        # #8 elle kontrolünde yanlış fix sayılanlar: yalnız test, link, yorum, stil, CI ve
        # bağımlılık düzeltmeleri; gitmoji önekleri (✏ yazım, 👷/💚 CI, ✅ test, 🔒 bağımlılık…).
        r"^tests?\b",
        r"\btests?:",
        r"\bfix(e[sd])?\s+(\w+\s+){0,3}tests?\b",
        r"\blinks?\b",
        r"\bcomments?\b",
        r"\bstyle\b",
        r"\bdependenc(y|ies)\b",
        r"\bdeps\b",
        r"\bappveyor\b",
        r"\b(github )?actions?\b",
        r"\bworkflows?\b",
        r"^(✏|👷|💚|✅|🔒|📝|⬆|🔧|🎨|:pencil2:|:construction_worker:|:green_heart:"
        r"|:white_check_mark:|:lock:|:memo:|:arrow_up:|:wrench:|:art:)",
    ]
    """Commit'in ilk satırında eşleşirse kalıp eşleşmesi fix sayılmaz; hata etiketi yine sayılır."""
    fix_subject_only: bool = False
    """True ise fix kalıpları yalnızca commit başlığında (ilk satır) aranır; gövdedeki "should
    fix #1" gibi geçişler fix sayılmaz."""
    bug_labels: list[str] = [
        "bug",
        "type: bug",
        "type:bug",
        "kind/bug",
        "kind: bug",
        "bugfix",
        "regression",
    ]
    """Bağlı issue'da bu etiketlerden biri varsa commit fix sayılır (büyük/küçük harf duyarsız)."""

    szz_variant: Literal["ma", "b"] = "ma"
    """`ma`: boşluk/yorum değişikliklerini ve meta commit'leri yok sayar; `b`: düz blame (FR-03)."""
    history_years: int | None = Field(default=None, gt=0)
    """SZZ yalnızca son N yıldaki fix'leri işler (en yeni commit'e göre); `None`: tüm geçmiş."""
    max_files_per_commit: int = Field(default=50, gt=0)
    """Daha fazla dosya değiştiren fix'ler atlanır; `ma` bu commit'leri blame'de de yok sayar."""
    source_extensions: list[str] = [".py"]
    """SZZ'nin blame ettiği kaynak dosya uzantıları."""
    test_path_patterns: list[str] = [
        r"(^|/)tests?/",
        r"(^|/)test_[^/]*\.py$",
        r"_tests?\.py$",
        r"(^|/)tests?\.py$",
        r"(^|/)conftest\.py$",
    ]
    """Eşleşen yollar SZZ'de kaynak sayılmaz; yalnız testlere dokunan fix'ler elenir."""

    @field_validator("fix_patterns", "fix_exclude_patterns", "test_path_patterns")
    @classmethod
    def _valid_regex(cls, patterns: list[str]) -> list[str]:
        for pattern in patterns:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError(f"geçersiz regex {pattern!r}: {exc}") from exc
        return patterns


class TrainingConfig(_Section):
    """Gatekeeper eğitimi: zaman sıralı bölme ve etiket gecikmesi (FR-10, #14)."""

    valid_fraction: float = Field(default=0.15, gt=0, lt=1)
    """Doğrulama kümesi: test öncesindeki commit'lerin payı (zaman sırasıyla)."""
    test_fraction: float = Field(default=0.2, gt=0, lt=1)
    """Test kümesi: en yeni commit'lerin payı."""
    label_delay_days: int = Field(default=90, ge=0)
    """Her kümenin bitişinden önceki bu kadar günün commit'leri bir önceki kümeye alınmaz:
    hataları henüz bulunmamış olabilir (etiket gecikmesi)."""
    calibration: Literal["none", "sigmoid", "isotonic"] = "sigmoid"
    """Skorların doğrulama kümesinde olasılığa çevrilme yöntemi (#18)."""

    @model_validator(mode="after")
    def _room_for_train(self) -> "TrainingConfig":
        if self.valid_fraction + self.test_fraction >= 1:
            raise ValueError("valid_fraction + test_fraction 1'den küçük olmalı")
        return self


class AegisConfig(_Section):
    gatekeeper: GatekeeperConfig = GatekeeperConfig()
    filters: FiltersConfig = FiltersConfig()
    memory: MemoryConfig = MemoryConfig()
    agents: dict[str, AgentConfig] = {}
    review: ReviewConfig = ReviewConfig()
    mining: MiningConfig = MiningConfig()
    training: TrainingConfig = TrainingConfig()

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
