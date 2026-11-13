"""Risk modelleri: LR, Random Forest, LightGBM (#15).

Üç model de aynı 14 Kamei özelliğiyle, zaman sıralı bölmenin (#14) eğitim kümesinde eğitilir.
Karar eşiği doğrulama kümesinde F1'i en yükseğe çıkaracak şekilde seçilir; test kümesi yalnızca
raporlama içindir. Bütçeye dayalı eşik ve kalibrasyon #18'de gelir.

- `lr`: log(1+x) dönüşümü + standartlaştırma + lojistik regresyon (Kamei'deki gibi çarpık
  dağılımlar için log dönüşümü),
- `rf`: Random Forest,
- `lightgbm`: gradient boosting.

Sınıf dengesizliği (#16): `none` veya `weights` (sınıf ağırlıkları); `undersample` eğitim
kümesindeki temiz commit'leri hatalı sayısına indirir.
"""

import pickle
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np
import polars as pl
from lightgbm import LGBMClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler

from aegis import __version__
from aegis.features.kamei import KAMEI
from aegis.gatekeeper.metrics import best_f1_threshold, evaluate
from aegis.gatekeeper.split import Split

ModelName = Literal["lr", "rf", "lightgbm"]
Imbalance = Literal["none", "weights", "undersample"]
MODELS: tuple[ModelName, ...] = ("lr", "rf", "lightgbm")
FEATURES: tuple[str, ...] = tuple(KAMEI)


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


def matrix(frame: pl.DataFrame) -> np.ndarray[Any, np.dtype[np.float64]]:
    # LR'deki log1p negatif değer almasın: tüm Kamei metrikleri tanım gereği ≥ 0.
    return frame.select(FEATURES).to_numpy().astype(np.float64).clip(min=0)


def effort(frame: pl.DataFrame) -> np.ndarray[Any, np.dtype[np.float64]]:
    """Efor = değişen satır sayısı; sıfır eforlu commit'ler 1 sayılır."""
    return (frame["la"] + frame["ld"]).clip(lower_bound=1).to_numpy().astype(np.float64)


def _undersample(train: pl.DataFrame, seed: int) -> pl.DataFrame:
    buggy = train.filter(pl.col("buggy"))
    clean = train.filter(~pl.col("buggy"))
    if buggy.height == 0 or clean.height <= buggy.height:
        return train
    return pl.concat([buggy, clean.sample(buggy.height, seed=seed)]).sort("as_of")


@dataclass
class TrainedModel:
    name: ModelName
    imbalance: Imbalance
    estimator: Any
    threshold: float
    valid: dict[str, float]
    test: dict[str, float]
    meta: dict[str, Any] = field(default_factory=dict)

    def predict_proba(self, frame: pl.DataFrame) -> np.ndarray[Any, np.dtype[np.float64]]:
        return np.asarray(self.estimator.predict_proba(matrix(frame))[:, 1], dtype=np.float64)

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


def train_model(
    split: Split, name: ModelName, *, imbalance: Imbalance = "none", seed: int = 0
) -> TrainedModel:
    train = _undersample(split.train, seed) if imbalance == "undersample" else split.train
    y_train = train["buggy"].to_numpy()
    if y_train.sum() == 0:
        raise ValueError("eğitim kümesinde hatalı commit yok")
    estimator = make_model(name, balanced=imbalance == "weights", seed=seed)
    estimator.fit(matrix(train), y_train)
    model = TrainedModel(name, imbalance, estimator, 0.5, {}, {})

    valid_prob = model.predict_proba(split.valid)
    model.threshold = best_f1_threshold(split.valid["buggy"].to_numpy(), valid_prob)
    model.valid = evaluate(
        split.valid["buggy"].to_numpy(), valid_prob, effort(split.valid), model.threshold
    )
    model.test = evaluate(
        split.test["buggy"].to_numpy(),
        model.predict_proba(split.test),
        effort(split.test),
        model.threshold,
    )
    model.meta = {
        "aegis_version": __version__,
        "trained_at": datetime.now(UTC).isoformat(),
        "features": list(FEATURES),
        "train_rows": train.height,
        "train_positives": int(y_train.sum()),
        "valid_start": split.valid_start.isoformat(),
        "test_start": split.test_start.isoformat(),
        "seed": seed,
    }
    return model
