"""Kalibrasyon, bütçeye dayalı eşik ve PR düzeyinde skor (FR-11, FR-13, #18).

- **Kalibrasyon:** Model skorları doğrulama kümesinde olasılığa çevrilir. `sigmoid` (Platt):
  log-odds üzerinde tek değişkenli lojistik regresyon; `isotonic`: monoton parçalı sabit
  eşleme. İkisi de sıralamayı korur (isotonic eşitlik üretebilir), yani ROC-AUC neredeyse aynı
  kalır; değişen, skorun "gerçek hata olasılığı" olarak okunabilmesidir.
- **Bütçe:** "PR'ların en fazla %X'i LLM'e gitsin" verildiğinde, doğrulama skorlarında
  `skor ≥ eşik` olanların payı X'i aşmayacak en küçük eşik seçilir. Bu eşiğin altı düşük
  banttır (LLM çalışmaz). Yüksek bant, bütçenin `high_share` kadarlık en riskli kısmıdır.
- **PR skoru:** PR etiketi "commit'lerinden en az biri hatalı" olduğundan, commit
  olasılıkları bağımsız sayılarak PR olasılığı `1 − Π(1 − pᵢ)` ile birleştirilir.
"""

import math
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
from numpy.typing import ArrayLike, NDArray

Method = Literal["none", "sigmoid", "isotonic"]
METHODS: tuple[Method, ...] = ("none", "sigmoid", "isotonic")
_EPS = 1e-6


def _logit(p: NDArray[np.float64]) -> NDArray[np.float64]:
    q = np.clip(p, _EPS, 1 - _EPS)
    return np.asarray(np.log(q / (1 - q)), dtype=np.float64)


@dataclass
class Calibrator:
    method: Method
    model: Any = None

    def apply(self, prob: ArrayLike) -> NDArray[np.float64]:
        p = np.asarray(prob, dtype=np.float64)
        if self.model is None:
            return p
        if self.method == "sigmoid":
            out = self.model.predict_proba(_logit(p).reshape(-1, 1))[:, 1]
        else:
            out = self.model.predict(p)
        return np.asarray(out, dtype=np.float64)


def fit_calibrator(method: Method, prob: ArrayLike, y_true: ArrayLike) -> Calibrator:
    """Doğrulama skorları ve etiketleriyle kalibratör kurar; tek sınıfta dönüşüm yapmaz."""
    p = np.asarray(prob, dtype=np.float64)
    y = np.asarray(y_true, dtype=int)
    if method == "none" or len(np.unique(y)) < 2:
        return Calibrator("none")
    if method == "sigmoid":
        from sklearn.linear_model import LogisticRegression

        lr = LogisticRegression(C=1e4, max_iter=1000).fit(_logit(p).reshape(-1, 1), y)
        return Calibrator("sigmoid", lr)
    from sklearn.isotonic import IsotonicRegression

    iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip").fit(p, y)
    return Calibrator("isotonic", iso)


def reliability(y_true: ArrayLike, prob: ArrayLike, bins: int = 10) -> list[list[float]]:
    """Eşit genişlikli kutular: [ortalama tahmin, gerçek hatalı payı, örnek sayısı]."""
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(prob, dtype=float)
    idx = np.minimum((p * bins).astype(int), bins - 1)
    out: list[list[float]] = []
    for b in range(bins):
        mask = idx == b
        if mask.any():
            out.append([float(p[mask].mean()), float(y[mask].mean()), float(mask.sum())])
    return out


def ece(y_true: ArrayLike, prob: ArrayLike, bins: int = 10) -> float:
    """Beklenen kalibrasyon hatası: kutu ağırlıklı |tahmin − gerçek| ortalaması."""
    rows = reliability(y_true, prob, bins)
    total = sum(n for _, _, n in rows)
    if total == 0:
        return math.nan
    return float(sum(n * abs(pred - real) for pred, real, n in rows) / total)


def budget_thresholds(
    scores: ArrayLike, max_llm_ratio: float, high_share: float = 0.5
) -> tuple[float, float]:
    """(düşük, yüksek) eşikleri: `skor ≥ düşük` payı en fazla `max_llm_ratio` olur.

    Yüksek eşik aynı kuralla `max_llm_ratio × high_share` payına göre seçilir.
    """
    if not 0 < max_llm_ratio <= 1 or not 0 < high_share <= 1:
        raise ValueError("max_llm_ratio ve high_share (0, 1] aralığında olmalı")
    s = np.sort(np.asarray(scores, dtype=float))
    if s.size == 0:
        raise ValueError("eşik için skor yok")

    def at_most(ratio: float) -> float:
        # Her benzersiz değer için `≥ değer` payı; payı oranı aşmayan en küçük değer.
        values = np.unique(s)
        share = 1 - np.searchsorted(s, values, side="left") / s.size
        ok = values[share <= ratio + 1e-12]
        return float(ok[0]) if ok.size else float(np.nextafter(s[-1], np.inf))

    low = at_most(max_llm_ratio)
    return low, max(low, at_most(max_llm_ratio * high_share))


def recall_threshold(scores: ArrayLike, y_true: ArrayLike, target_recall: float) -> float:
    """En az `target_recall` doğrulama recall'ı veren en yüksek eşik.

    Skoru eşik veya üstünde olan PR'lar/commit'ler gönderilir. Hata etiketi yoksa güvenli
    varsayımla tüm örnekleri göndeririz. Aynı skor değerindeki örnekler birlikte tutulur.
    """
    if not 0 < target_recall <= 1:
        raise ValueError("target_recall (0, 1] aralığında olmalı")
    score = np.asarray(scores, dtype=float)
    labels = np.asarray(y_true, dtype=bool)
    if score.ndim != 1 or labels.ndim != 1 or score.size == 0 or score.size != labels.size:
        raise ValueError("scores ve y_true boş olmayan, aynı uzunlukta 1 boyutlu diziler olmalı")
    if not np.isfinite(score).all():
        raise ValueError("scores sonlu olmalı")
    if not labels.any():
        return float(score.min())
    for threshold in np.unique(score)[::-1]:
        recall = float(labels[score >= threshold].sum() / labels.sum())
        if recall + 1e-12 >= target_recall:
            return float(threshold)
    return float(score.min())


def pr_score(commit_probs: ArrayLike) -> float:
    """PR'daki en az bir commit'in hatalı olma olasılığı (bağımsızlık varsayımıyla)."""
    p = np.clip(np.asarray(commit_probs, dtype=float), 0.0, 1.0)
    if p.size == 0:
        return 0.0
    return float(1 - np.prod(1 - p))
