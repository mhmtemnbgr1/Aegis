"""Kamei vd. (2013) değişiklik metrikleri (FR-04, #10).

Her metrik `(change, history, *, as_of)` imzalı bir fonksiyondur (bkz. `aegis.features.Feature`).
Yalnızca değişikliğin kendisine bakan metrikler de `as_of` alır; arayüz tek tiptir ve geçmişe
bakan her erişim `ChangeHistory` üzerinden `as_of` ile sınırlanır.

| Grup | Metrik | Tanım |
| --- | --- | --- |
| Yayılım | NS | Değişen alt sistem (en üst dizin) sayısı |
| | ND | Değişen dizin sayısı |
| | NF | Değişen dosya sayısı |
| | Entropy | Değişen satırların dosyalara dağılımı: −Σ pᵢ log₂ pᵢ |
| Boyut | LA, LD | Eklenen / silinen satırlar |
| | LT | Değişen dosyaların değişiklikten önceki toplam satır sayısı |
| Amaç | FIX | Değişiklik bir hata düzeltmesi mi (0/1) |
| Geçmiş | NDEV | Değişen dosyalara daha önce dokunan farklı geliştirici sayısı |
| | AGE | Değişen dosyaların son değişikliğinden bu yana geçen ortalama gün |
| | NUC | Değişen dosyalara daha önce dokunan farklı commit sayısı |
| Deneyim | EXP | Geliştiricinin önceki commit sayısı |
| | REXP | Yıla göre ağırlıklı deneyim: n yıl önceki commit 1/(n+1) sayılır |
| | SEXP | Geliştiricinin değişen alt sistemlere önceki commit sayısı |
"""

import math
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta
from typing import Any

import polars as pl

from aegis.features.base import Feature
from aegis.features.history import Change, ChangeHistory, directory, iter_changes, subsystem

_DAY = timedelta(days=1)
_YEAR = timedelta(days=365.25)


def ns(change: Change, history: ChangeHistory, *, as_of: datetime) -> float:
    return len({subsystem(f.path) for f in change.files})


def nd(change: Change, history: ChangeHistory, *, as_of: datetime) -> float:
    return len({directory(f.path) for f in change.files})


def nf(change: Change, history: ChangeHistory, *, as_of: datetime) -> float:
    return len(change.files)


def entropy(change: Change, history: ChangeHistory, *, as_of: datetime) -> float:
    churn = [f.added + f.deleted for f in change.files]
    total = sum(churn)
    if total == 0:
        return 0.0
    h = -sum(c / total * math.log2(c / total) for c in churn if c)
    return h if h > 0 else 0.0  # tek dosyada -0.0 yerine 0.0


def la(change: Change, history: ChangeHistory, *, as_of: datetime) -> float:
    return sum(f.added for f in change.files)


def ld(change: Change, history: ChangeHistory, *, as_of: datetime) -> float:
    return sum(f.deleted for f in change.files)


def lt(change: Change, history: ChangeHistory, *, as_of: datetime) -> float:
    return sum(history.line_count(f.prior_path, as_of) for f in change.files if f.prior_path)


def fix(change: Change, history: ChangeHistory, *, as_of: datetime) -> float:
    return float(change.is_fix)


def _prior(change: Change) -> Iterable[str]:
    return {f.prior_path for f in change.files if f.prior_path}


def ndev(change: Change, history: ChangeHistory, *, as_of: datetime) -> float:
    devs: set[str] = set()
    for path in _prior(change):
        devs.update(history.file_events(path, as_of)[2])
    return len(devs)


def age(change: Change, history: ChangeHistory, *, as_of: datetime) -> float:
    gaps = [
        (as_of - times[-1]) / _DAY
        for path in _prior(change)
        if (times := history.file_events(path, as_of)[0])
    ]
    return sum(gaps) / len(gaps) if gaps else 0.0


def nuc(change: Change, history: ChangeHistory, *, as_of: datetime) -> float:
    shas: set[str] = set()
    for path in _prior(change):
        shas.update(history.file_events(path, as_of)[1])
    return len(shas)


def exp(change: Change, history: ChangeHistory, *, as_of: datetime) -> float:
    return len(history.developer_times(change.developer, as_of))


def rexp(change: Change, history: ChangeHistory, *, as_of: datetime) -> float:
    return sum(
        1 / (int((as_of - t) / _YEAR) + 1) for t in history.developer_times(change.developer, as_of)
    )


def sexp(change: Change, history: ChangeHistory, *, as_of: datetime) -> float:
    subsystems = {subsystem(f.path) for f in change.files}
    return len(history.developer_subsystem_shas(change.developer, subsystems, as_of))


KAMEI: Mapping[str, Feature] = {
    "ns": ns,
    "nd": nd,
    "nf": nf,
    "entropy": entropy,
    "la": la,
    "ld": ld,
    "lt": lt,
    "fix": fix,
    "ndev": ndev,
    "age": age,
    "nuc": nuc,
    "exp": exp,
    "rexp": rexp,
    "sexp": sexp,
}
"""14 metrik, Kamei vd. (2013) sırasıyla."""


def kamei_metrics(change: Change, history: ChangeHistory, *, as_of: datetime) -> dict[str, float]:
    return {name: float(f(change, history, as_of=as_of)) for name, f in KAMEI.items()}


KAMEI_SCHEMA: dict[str, pl.DataType] = {
    "repo": pl.String(),
    "sha": pl.String(),
    "as_of": pl.Datetime("us", "UTC"),
    **{name: pl.Float64() for name in KAMEI},
}


def compute_kamei(
    commits: pl.DataFrame, files: pl.DataFrame, *, only_shas: set[str] | None = None
) -> pl.DataFrame:
    """Commit başına 14 metrik; artımlı çalışmada yalnızca `only_shas` hesaplanır.

    Geçmiş özellikleri için `ChangeHistory` tüm commit'lerden kurulur; hedef commit'lerin kendisi
    metriğe katılmaz çünkü her sorgu `as_of` zamanıyla sınırlandırılır.
    """
    history = ChangeHistory.from_frames(commits, files)
    repo = commits["repo"][0] if commits.height else ""
    targets = (
        commits.filter(pl.col("sha").is_in(only_shas)) if only_shas is not None else commits
    )
    rows: list[dict[str, Any]] = [
        {"repo": repo, "sha": sha, "as_of": time, **kamei_metrics(change, history, as_of=time)}
        for sha, time, _, change in iter_changes(targets, files)
    ]
    return pl.DataFrame(rows, schema=KAMEI_SCHEMA)
