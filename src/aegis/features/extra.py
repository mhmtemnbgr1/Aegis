"""Aegis'e özgü değişiklik özellikleri (FR-12): riskli yol ve test değişim oranı.

İkisi de yalnızca değişikliğin kendisine (dosya yolları ve satır sayıları) bakar; geçmişi
okumaz, bu yüzden `as_of` kuralından etkilenmez ve sızıntı riski taşımaz.

- `risky_files`: Yolunda riskli bir kelime (`auth`, `db`, `payment`… ; sezgisel kuralla aynı
  liste, `[gatekeeper.heuristic].risky_paths`) geçen değişmiş dosya sayısı.
- `test_ratio`: Değişen satırların test dosyalarına düşen payı (`[mining].test_path_patterns`);
  hiç satır değişmediyse 0.

Hafızadan gelen "geçmiş hata kartı sayısı" özelliği #29'da eklenecek.
"""

import re
from collections.abc import Iterable

from aegis.features.history import Change

EXTRA: tuple[str, ...] = ("risky_files", "test_ratio")
_WORD_SPLIT = re.compile(r"[^a-z0-9]+")


def risky_files(change: Change, risky: Iterable[str]) -> float:
    words = {w.lower() for w in risky}
    return float(sum(1 for f in change.files if set(_WORD_SPLIT.split(f.path.lower())) & words))


def test_ratio(change: Change, test_patterns: Iterable[str]) -> float:
    patterns = [re.compile(p) for p in test_patterns]
    total = sum(f.added + f.deleted for f in change.files)
    if total == 0:
        return 0.0
    tests = sum(
        f.added + f.deleted for f in change.files if any(p.search(f.path) for p in patterns)
    )
    return tests / total


def extra_metrics(
    change: Change, *, risky: Iterable[str], test_patterns: Iterable[str]
) -> dict[str, float]:
    return {
        "risky_files": risky_files(change, risky),
        "test_ratio": test_ratio(change, test_patterns),
    }
