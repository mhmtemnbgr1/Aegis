"""Gatekeeper değerlendirme metrikleri (#15).

Sınıflandırma: ROC-AUC, PR-AUC (ortalama kesinlik), F1, MCC.

Kalibrasyon (#18): Brier skoru ve beklenen kalibrasyon hatası (ECE, 10 kutu).

Efora duyarlı metrikler (Kamei vd. 2013; JITLine 2021): efor = değişen satır sayısı (LA + LD).
Commit'ler tahmin edilen risk yoğunluğuna (olasılık / efor) göre azalan sırada incelenir.

- **Recall@%20 efor:** Toplam eforun ilk %20'si harcandığında bulunan hatalı commit'lerin payı.
- **Popt:** Model eğrisinin (x: kümülatif efor payı, y: kümülatif hatalı payı) altında kalan
  alanın, en iyi (gerçek yoğunluğa göre) ve en kötü sıralama arasında normalleştirilmiş hali:
  Popt = 1 − (A_en_iyi − A_model) / (A_en_iyi − A_en_kötü). 1 en iyi, 0 en kötü sıralamadır.
"""

import math

import numpy as np
from numpy.typing import ArrayLike, NDArray
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    f1_score,
    matthews_corrcoef,
    roc_auc_score,
)

from aegis.gatekeeper.calibration import ece

EFFORT_BUDGET = 0.2


def _curve_area(
    order: NDArray[np.intp], y: NDArray[np.float64], effort: NDArray[np.float64]
) -> float:
    """Sıralamaya göre (kümülatif efor payı, kümülatif hatalı payı) eğrisinin altındaki alan."""
    x = np.concatenate([[0.0], np.cumsum(effort[order]) / effort.sum()])
    hit = np.concatenate([[0.0], np.cumsum(y[order]) / y.sum()])
    return float(np.trapezoid(hit, x))


def recall_at_effort(
    y_true: ArrayLike, score: ArrayLike, effort: ArrayLike, budget: float = EFFORT_BUDGET
) -> float:
    """Risk yoğunluğu sırasıyla eforun `budget` kadarı harcandığında bulunan hatalı payı.

    Bütçeyi aşan ilk commit sayılmaz (yalnızca tamamen incelenenler).
    """
    y = np.asarray(y_true, dtype=float)
    e = np.asarray(effort, dtype=float)
    if y.sum() == 0 or e.sum() == 0:
        return math.nan
    order = np.argsort(-np.asarray(score, dtype=float) / e, kind="stable")
    spent = np.cumsum(e[order]) / e.sum()
    inspected = spent <= budget + 1e-12
    return float(y[order][inspected].sum() / y.sum())


def popt(y_true: ArrayLike, score: ArrayLike, effort: ArrayLike) -> float:
    y = np.asarray(y_true, dtype=float)
    e = np.asarray(effort, dtype=float)
    if y.sum() == 0 or e.sum() == 0:
        return math.nan
    density = y / e
    best = _curve_area(np.argsort(-density, kind="stable"), y, e)
    worst = _curve_area(np.argsort(density, kind="stable"), y, e)
    model = _curve_area(np.argsort(-np.asarray(score, dtype=float) / e, kind="stable"), y, e)
    if best == worst:
        return math.nan
    return float(1 - (best - model) / (best - worst))


def evaluate(
    y_true: ArrayLike, prob: ArrayLike, effort: ArrayLike, threshold: float = 0.5
) -> dict[str, float]:
    """Tüm metrikler. Tek sınıflı kümelerde tanımsız olanlar NaN döner."""
    y = np.asarray(y_true, dtype=int)
    p = np.asarray(prob, dtype=float)
    pred = (p >= threshold).astype(int)
    both = len(np.unique(y)) == 2
    return {
        "roc_auc": float(roc_auc_score(y, p)) if both else math.nan,
        "pr_auc": float(average_precision_score(y, p)) if both else math.nan,
        "f1": float(f1_score(y, pred, zero_division=0)),
        "mcc": float(matthews_corrcoef(y, pred)) if both else math.nan,
        "recall_at_20_effort": recall_at_effort(y, p, effort),
        "popt": popt(y, p, effort),
        "brier": float(brier_score_loss(y, p)) if len(y) else math.nan,
        "ece": ece(y, p),
        "positives": float(y.sum()),
        "n": float(len(y)),
    }


def best_f1_threshold(y_true: ArrayLike, prob: ArrayLike) -> float:
    """Doğrulama kümesinde F1'i en yüksek yapan eşik (eşitlikte daha yüksek eşik)."""
    y = np.asarray(y_true, dtype=int)
    p = np.asarray(prob, dtype=float)
    if y.sum() == 0:
        return 0.5
    best_t, best_f = 0.5, -1.0
    for t in np.unique(p):
        f = float(f1_score(y, (p >= t).astype(int), zero_division=0))
        if f >= best_f:
            best_t, best_f = float(t), f
    return best_t
