"""Özellik fonksiyonlarının ortak arayüzü (FR-18, #72)."""

from datetime import datetime
from typing import Protocol

from aegis.features.history import Change, ChangeHistory


class Feature(Protocol):
    """Bir değişiklik için tek bir sayısal özellik.

    `as_of` zorunludur; geçmiş yalnızca `history` üzerinden ve `as_of`'tan önce commit'lenmiş
    olaylarla okunur. Değişikliğin kendisine bakan özellikler de aynı imzayı taşır.
    """

    def __call__(self, change: Change, history: ChangeHistory, *, as_of: datetime) -> float: ...
