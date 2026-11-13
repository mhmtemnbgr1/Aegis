"""Risk skorunun açıklaması: en etkili 3 özellik ve Türkçe metin (FR-14, #19).

`shap` paketi yerine her model için kesin ya da yerleşik yöntem kullanılır (ek bağımlılık yok):

- `lr`: Doğrusal SHAP. Özellikler log1p + standartlaştırmadan geçtiği için eğitim ortalaması 0'dır;
  katkı = katsayı × standart değer (log-odds). Özellik bağımsızlığı varsayımıyla SHAP'a eşittir.
- `lightgbm`: LightGBM'in yerleşik TreeSHAP'ı (`pred_contrib=True`, log-odds). Kesin SHAP.
- `rf`: Saabas katkıları. Her ağaçta kökten yaprağa giderken olasılıktaki değişim, o düğümde
  bölen özelliğe yazılır ve ağaçlar üzerinden ortalaması alınır (olasılık ölçeği). SHAP'a yakın
  bir yaklaşımdır, ancak SHAP'ın tutarlılık garantisi yoktur.

Her yöntemde katkılar ile taban değerin toplamı, modelin ham çıktısına eşittir. Açıklama
kalibrasyondan önceki ham modele aittir; kalibrasyon sıralamayı koruduğu için yön değişmez.
"""

from dataclasses import dataclass
from typing import Any

import numpy as np
import polars as pl
from numpy.typing import NDArray

TOP_K = 3


def _fmt(v: float) -> str:
    return f"{v:,.0f}".replace(",", ".")


TEXT: dict[str, Any] = {
    "ns": lambda v: f"{_fmt(v)} alt sisteme dokunuyor",
    "nd": lambda v: f"{_fmt(v)} dizinde değişiklik var",
    "nf": lambda v: f"{_fmt(v)} dosya değişti",
    "entropy": lambda v: (
        f"değişiklik dosyalara {'dağınık' if v >= 1 else 'toplu'} (entropi {v:.2f})"
    ),
    "la": lambda v: f"{_fmt(v)} satır eklendi",
    "ld": lambda v: f"{_fmt(v)} satır silindi",
    "lt": lambda v: f"değişen dosyalar önceden toplam {_fmt(v)} satırdı",
    "fix": lambda v: "değişiklik bir hata düzeltmesi" if v else "değişiklik hata düzeltmesi değil",
    "ndev": lambda v: f"bu dosyalara daha önce {_fmt(v)} farklı geliştirici dokunmuş",
    "age": lambda v: f"dosyalar ortalama {_fmt(v)} gündür değişmemişti",
    "nuc": lambda v: f"bu dosyalar daha önce {_fmt(v)} commit'te değiştirilmiş",
    "exp": lambda v: f"yazarın bu repoda {_fmt(v)} önceki commit'i var",
    "rexp": lambda v: f"yazarın yakın dönem deneyimi {v:.1f} (yeni commit'ler daha ağır)",
    "sexp": lambda v: f"yazarın bu alt sistemlerde {_fmt(v)} önceki commit'i var",
    "risky_files": lambda v: f"{_fmt(v)} dosya riskli bir yolda (auth, db, payment…)",
    "test_ratio": lambda v: f"değişen satırların %{100 * v:.0f}'i test kodunda",
    "mem_func_bugs": lambda v: f"değişen fonksiyonlarda geçmişte {_fmt(v)} hata düzeltilmiş",
    "mem_file_bugs": lambda v: f"değişen dosyalarda geçmişte {_fmt(v)} hata düzeltilmiş",
    "n_commits": lambda v: f"PR {_fmt(v)} commit içeriyor",
    "n_authors": lambda v: f"PR'da {_fmt(v)} farklı yazar var",
}
"""Özellik adı → değeri içeren Türkçe cümle."""


@dataclass(frozen=True)
class Explanation:
    feature: str
    value: float
    effect: float
    """Skora katkı: pozitifse riski artırır. Ölçek modele göre log-odds ya da olasılık."""

    @property
    def text(self) -> str:
        direction = "riski artırıyor" if self.effect > 0 else "riski azaltıyor"
        return f"{TEXT[self.feature](self.value)} ({direction})"


def _linear(estimator: Any, x: NDArray[np.float64]) -> tuple[NDArray[np.float64], float]:
    log, scaler, lr = (step for _, step in estimator.steps)
    z = scaler.transform(log.transform(x))
    return np.asarray(z * lr.coef_[0], dtype=np.float64), float(lr.intercept_[0])


def _lightgbm(estimator: Any, x: NDArray[np.float64]) -> tuple[NDArray[np.float64], float]:
    out = np.asarray(estimator.predict(x, pred_contrib=True), dtype=np.float64)
    return out[:, :-1], float(out[0, -1]) if len(out) else 0.0


def _saabas(estimator: Any, x: NDArray[np.float64]) -> tuple[NDArray[np.float64], float]:
    total = np.zeros_like(x, dtype=np.float64)
    base = 0.0
    for tree in estimator.estimators_:
        t = tree.tree_
        value = t.value[:, 0, :]
        prob = value[:, 1] / value.sum(axis=1)
        parent = np.full(t.node_count, -1)
        for node in range(t.node_count):
            for child in (t.children_left[node], t.children_right[node]):
                if child != -1:
                    parent[child] = node
        # Kök dışındaki her düğüm: ebeveynden bu düğüme geçişte olasılık değişimi, ebeveynin
        # böldüğü özelliğe yazılır. Bir örneğin katkısı = yolundaki düğümlerin toplamı.
        nodes = np.flatnonzero(parent >= 0)
        delta = np.zeros((t.node_count, x.shape[1]))
        delta[nodes, t.feature[parent[nodes]]] = prob[nodes] - prob[parent[nodes]]
        total += np.asarray(tree.decision_path(x.astype(np.float32)) @ delta)
        base += prob[0]
    n = len(estimator.estimators_)
    return total / n, base / n


def _features(model: Any) -> tuple[str, ...]:
    from aegis.gatekeeper.model import FEATURES

    return tuple(getattr(model, "features", FEATURES))


def contributions(model: Any, frame: pl.DataFrame) -> tuple[NDArray[np.float64], float]:
    """(n × özellik) katkı matrisi ve taban değer; katkılar + taban = ham model çıktısı."""
    from aegis.gatekeeper.model import matrix

    x = matrix(frame, _features(model))
    if model.name == "lr":
        return _linear(model.estimator, x)
    if model.name == "lightgbm":
        return _lightgbm(model.estimator, x)
    if model.name == "rf":
        return _saabas(model.estimator, x)
    raise ValueError(f"açıklama desteklenmiyor: {model.name}")


def explain(
    model: Any, frame: pl.DataFrame, k: int = TOP_K, *, increasing_only: bool = False
) -> list[list[Explanation]]:
    """Her satır için mutlak katkısı en büyük `k` özellik.

    `increasing_only`: yalnızca riski artıran (pozitif katkılı) özellikler, en büyükten başlayarak.
    PR yorumunda bu kullanılır: ilişkili özellikler (ör. NF, ND, LA) doğrusal modelde ters işaretli
    katsayı alabildiği için "5 dosya değişti (riski azaltıyor)" gibi sezgiye aykırı cümleler çıkar.
    """
    features = _features(model)
    phi, _ = contributions(model, frame)
    x = frame.select(features).to_numpy().astype(np.float64)
    out: list[list[Explanation]] = []
    for row, values in zip(phi, x, strict=True):
        key = -row if increasing_only else -np.abs(row)
        top = [i for i in np.argsort(key, kind="stable") if not increasing_only or row[i] > 0][:k]
        out.append([Explanation(features[i], float(values[i]), float(row[i])) for i in top])
    return out


def explain_pr(model: Any, commits: pl.DataFrame, k: int = TOP_K) -> list[Explanation]:
    """PR açıklaması: en riskli commit'te riski en çok artıran `k` özellik (FR-14).

    PR skorunu en çok belirleyen commit en riskli olandır; açıklaması PR'ınki sayılır.
    """
    if commits.height == 0:
        return []
    riskiest = int(np.argmax(model.predict_proba(commits)))
    return explain(model, commits[riskiest], k, increasing_only=True)[0]
