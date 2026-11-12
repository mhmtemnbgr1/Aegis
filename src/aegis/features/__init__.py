"""Gatekeeper özellikleri ve zaman kuralı (`as_of`).

Kural (FR-18): her özellik fonksiyonu `(change, history, *, as_of)` imzasını taşır ve geçmişi
yalnızca `ChangeHistory` üzerinden, `as_of`'tan önce commit'lenmiş olaylarla sınırlı okur.
"""

from aegis.features.base import Feature
from aegis.features.history import Change, ChangeHistory, FileChange, developer_id
from aegis.features.kamei import KAMEI, compute_kamei, kamei_metrics

__all__ = [
    "KAMEI",
    "Change",
    "ChangeHistory",
    "Feature",
    "FileChange",
    "compute_kamei",
    "developer_id",
    "kamei_metrics",
]
