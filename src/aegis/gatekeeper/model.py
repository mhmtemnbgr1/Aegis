"""Risk modelleri: LR, Random Forest, LightGBM (#15).

Üç model de aynı 14 Kamei özelliğiyle, zaman sıralı bölmenin (#14) eğitim kümesinde eğitilir.
Ham skorlar doğrulama kümesinde kalibre edilir (#18, `calibration`). Karar eşiği doğrulama
kümesinde F1'i en yükseğe çıkaracak şekilde seçilir; bütçeye dayalı bant eşikleri doğrulama
skorlarının dağılımından hesaplanır. Test kümesi yalnızca raporlama içindir.

- `lr`: log(1+x) dönüşümü + standartlaştırma + lojistik regresyon (Kamei'deki gibi çarpık
  dağılımlar için log dönüşümü),
- `rf`: Random Forest,
- `lightgbm`: gradient boosting.

Sınıf dengesizliği (#16): `none` veya `weights` (sınıf ağırlıkları); `undersample` eğitim
kümesindeki temiz commit'leri hatalı sayısına indirir; `smote` hatalı commit'leri sentetik
örneklerle temiz sayısına çıkarır. Yeniden örnekleme yalnızca eğitim kümesine uygulanır.
"""

import math
import pickle
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np
import polars as pl
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler

from aegis import __version__
from aegis.features.extra import EXTRA
from aegis.features.kamei import KAMEI
from aegis.gatekeeper.calibration import (
    Calibrator,
    Method,
    budget_thresholds,
    fit_calibrator,
    pr_score,
    reliability,
)
from aegis.gatekeeper.explain import Explanation, explain_pr
from aegis.gatekeeper.metrics import best_f1_threshold, evaluate
from aegis.gatekeeper.split import Split

ModelName = Literal["lr", "rf", "lightgbm"]
Imbalance = Literal["none", "weights", "undersample", "smote"]
IMBALANCE: tuple[Imbalance, ...] = ("none", "weights", "undersample", "smote")
MODELS: tuple[ModelName, ...] = ("lr", "rf", "lightgbm")
FEATURES: tuple[str, ...] = tuple(KAMEI)
"""Yalnızca 14 Kamei metriği (taban çizgisi)."""
FULL_FEATURES: tuple[str, ...] = (*KAMEI, *EXTRA)
"""Kamei + Aegis'e özgü diff özellikleri: riskli yol, test değişim oranı (FR-12)."""


def make_model(name: ModelName, *, balanced: bool = False, seed: int = 0) -> Any:
    weight = "balanced" if balanced else None
    if name == "lr":
        return make_pipeline(
            FunctionTransformer(np.log1p),
            StandardScaler(),
            LogisticRegression(max_iter=2000, class_weight=weight, random_state=seed),
        )
    if name == "rf":
        return RandomForestClassifier(
            n_estimators=300,
            min_samples_leaf=2,
            class_weight=weight,
            n_jobs=-1,
            random_state=seed,
        )
    if name == "lightgbm":
        # Geç içe aktarma: macOS'ta libomp gerektirir; yalnızca bu model istendiğinde yüklenir.
        from lightgbm import LGBMClassifier

        return LGBMClassifier(
            n_estimators=300,
            learning_rate=0.05,
            num_leaves=31,
            min_child_samples=10,
            class_weight=weight,
            random_state=seed,
            verbose=-1,
        )
    raise ValueError(f"bilinmeyen model: {name}")


def matrix(
    frame: pl.DataFrame, features: tuple[str, ...] = FEATURES
) -> np.ndarray[Any, np.dtype[np.float64]]:
    # LR'deki log1p negatif değer almasın: tüm Kamei metrikleri tanım gereği ≥ 0.
    return frame.select(features).to_numpy().astype(np.float64).clip(min=0)


def effort(frame: pl.DataFrame) -> np.ndarray[Any, np.dtype[np.float64]]:
    """Efor = değişen satır sayısı; sıfır eforlu commit'ler 1 sayılır."""
    return (frame["la"] + frame["ld"]).clip(lower_bound=1).to_numpy().astype(np.float64)


def _undersample(train: pl.DataFrame, seed: int) -> pl.DataFrame:
    buggy = train.filter(pl.col("buggy"))
    clean = train.filter(~pl.col("buggy"))
    if buggy.height == 0 or clean.height <= buggy.height:
        return train
    return pl.concat([buggy, clean.sample(buggy.height, seed=seed)]).sort("as_of")


def smote(
    x: np.ndarray[Any, np.dtype[np.float64]],
    y: np.ndarray[Any, Any],
    *,
    k: int = 5,
    seed: int = 0,
) -> tuple[np.ndarray[Any, np.dtype[np.float64]], np.ndarray[Any, Any]]:
    """SMOTE (Chawla vd. 2002): azınlık örneği ile k en yakın azınlık komşusu arasında rastgele
    bir noktada sentetik örnek üretir; sınıflar eşitlenene kadar."""
    from sklearn.neighbors import NearestNeighbors

    minority = x[y.astype(bool)]
    need = int((~y.astype(bool)).sum()) - minority.shape[0]
    if need <= 0 or minority.shape[0] < 2:
        return x, y
    rng = np.random.default_rng(seed)
    k = min(k, minority.shape[0] - 1)
    # Özellikler log ölçeğinde karşılaştırılır; Kamei metrikleri çok çarpık.
    neighbors = NearestNeighbors(n_neighbors=k + 1).fit(np.log1p(minority))
    idx = neighbors.kneighbors(np.log1p(minority), return_distance=False)[:, 1:]
    base = rng.integers(0, minority.shape[0], need)
    other = idx[base, rng.integers(0, k, need)]
    gap = rng.random((need, 1))
    synthetic = minority[base] + gap * (minority[other] - minority[base])
    return np.vstack([x, synthetic]), np.concatenate([y, np.ones(need, dtype=y.dtype)])


@dataclass
class TrainedModel:
    name: ModelName
    imbalance: Imbalance
    estimator: Any
    threshold: float
    valid: dict[str, float]
    test: dict[str, float]
    meta: dict[str, Any] = field(default_factory=dict)
    calibrator: Calibrator = field(default_factory=lambda: Calibrator("none"))
    valid_scores: list[float] = field(default_factory=list)
    """Doğrulama kümesinin kalibre skorları; bütçe eşikleri bunlardan hesaplanır."""
    budget: dict[str, dict[str, float]] = field(default_factory=dict)
    """Test kümesinde, doğrulamadan seçilen bütçe eşiğiyle LLM'e giden pay ve yakalanan hatalar."""
    reliability: list[list[float]] = field(default_factory=list)
    features: tuple[str, ...] = FEATURES
    """Modelin girdi sütunları: commit düzeyinde 14 Kamei metriği, PR düzeyinde ekleriyle (#73)."""
    """Test kümesi kalibrasyon eğrisi: [ortalama tahmin, gerçek hatalı payı, örnek sayısı]."""

    def raw_proba(self, frame: pl.DataFrame) -> np.ndarray[Any, np.dtype[np.float64]]:
        x = matrix(frame, getattr(self, "features", FEATURES))
        return np.asarray(self.estimator.predict_proba(x)[:, 1], dtype=np.float64)

    def predict_proba(self, frame: pl.DataFrame) -> np.ndarray[Any, np.dtype[np.float64]]:
        """Kalibre edilmiş hata olasılıkları (commit başına)."""
        return self.calibrator.apply(self.raw_proba(frame))

    def score_pr(self, commits: pl.DataFrame) -> float:
        """Bir PR'ın commit'lerinden en az birinin hatalı olma olasılığı (FR-11)."""
        return pr_score(self.predict_proba(commits))

    def explain_pr(self, commits: pl.DataFrame, k: int = 3) -> list[Explanation]:
        """Skoru en çok etkileyen `k` özellik ve Türkçe metinleri (FR-14)."""
        return explain_pr(self, commits, k)

    def thresholds(self, max_llm_ratio: float, high_share: float = 0.5) -> tuple[float, float]:
        """Bütçeye göre (düşük, yüksek) bant eşikleri (FR-13)."""
        return budget_thresholds(self.valid_scores, max_llm_ratio, high_share)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as fh:
            pickle.dump(self, fh)

    @staticmethod
    def load(path: Path) -> "TrainedModel":
        with path.open("rb") as fh:
            model = pickle.load(fh)  # nosec B301: yalnızca kendi ürettiğimiz dosyalar
        if not isinstance(model, TrainedModel):
            raise TypeError(f"{path} bir Aegis modeli değil")
        return model


BUDGETS = (0.1, 0.2, 0.3, 0.5)


def train_model(
    split: Split,
    name: ModelName,
    *,
    imbalance: Imbalance = "none",
    calibration: Method = "sigmoid",
    seed: int = 0,
    features: tuple[str, ...] = FEATURES,
) -> TrainedModel:
    train = _undersample(split.train, seed) if imbalance == "undersample" else split.train
    y_train = train["buggy"].to_numpy()
    if y_train.sum() == 0:
        raise ValueError("eğitim kümesinde hatalı commit yok")
    estimator = make_model(name, balanced=imbalance == "weights", seed=seed)
    x_train = matrix(train, features)
    if imbalance == "smote":
        x_train, y_train = smote(x_train, y_train, seed=seed)
    estimator.fit(x_train, y_train)
    model = TrainedModel(name, imbalance, estimator, 0.5, {}, {}, features=features)

    y_valid = split.valid["buggy"].to_numpy()
    model.calibrator = fit_calibrator(calibration, model.raw_proba(split.valid), y_valid)
    valid_prob = model.predict_proba(split.valid)
    model.valid_scores = [float(v) for v in valid_prob]
    model.threshold = best_f1_threshold(y_valid, valid_prob)
    model.valid = evaluate(y_valid, valid_prob, effort(split.valid), model.threshold)
    # Test kümesi boş olabilir (ör. kayan pencerede test ayrıca puanlanır, #21).
    if split.test.height:
        y_test = split.test["buggy"].to_numpy()
        test_prob = model.predict_proba(split.test)
        model.test = evaluate(y_test, test_prob, effort(split.test), model.threshold)
        model.reliability = reliability(y_test, test_prob)
        for ratio in BUDGETS:
            low, _ = model.thresholds(ratio)
            sent = test_prob >= low
            model.budget[f"{ratio:g}"] = {
                "threshold": low,
                "llm_share": float(sent.mean()),
                "recall": float(sent[y_test.astype(bool)].mean()) if y_test.any() else math.nan,
            }
    model.meta = {
        "aegis_version": __version__,
        "trained_at": datetime.now(UTC).isoformat(),
        "features": list(features),
        "train_rows": len(y_train),
        "train_positives": int(y_train.sum()),
        "train_repos": sorted(set(train["repo"])) if "repo" in train.columns else [],
        "valid_start": split.valid_start.isoformat(),
        "test_start": split.test_start.isoformat(),
        "seed": seed,
        "calibration": model.calibrator.method,
    }
    return model
