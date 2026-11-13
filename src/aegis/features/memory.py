"""Hafıza sinyali: değişikliğin dokunduğu koddaki geçmiş hata kartı sayısı (FR-12, FR-18, #29).

- `mem_func_bugs`: değişen fonksiyonlardan en az birini daha önce düzeltmiş kart sayısı,
- `mem_file_bugs`: değişen dosyalardan en az birine daha önce dokunmuş kart sayısı.

**Zaman kuralı:** Yalnızca `fix_date < as_of` olan kartlar sayılır (kesin küçük): bir fix commit'i
kendi kartını göremez, geleceğe tarihli bir kart değeri değiştirmez.

Fonksiyonlar `(dosya yolu, kısa ad)` çiftiyle eşlenir. Kartlardaki nitelikli adlar (`ast`,
`app.pool.Pool.release`) dosyalarına göre kısaltılır (`app/pool.py`, `release`); böylece
madencilikteki lizard fonksiyon adlarıyla (`functions.parquet`) ve çalışma anındaki `ast`
adlarıyla aynı anahtar
kullanılır. Aynı dosyada aynı adlı iki metot (ör. iki sınıfta `close`) tek anahtara düşer; bu,
sayımı biraz şişirebilir.
"""

from bisect import bisect_left
from collections.abc import Iterable
from datetime import datetime

from aegis.memory.cards import BugCard
from aegis.memory.chunk import module_name

MEMORY: tuple[str, ...] = ("mem_func_bugs", "mem_file_bugs")


def card_function_keys(card: BugCard) -> set[tuple[str, str]]:
    """Kartın düzelttiği fonksiyonların `(dosya, kısa ad)` anahtarları."""
    modules = sorted(((module_name(f), f) for f in card.files), key=lambda m: -len(m[0]))
    keys: set[tuple[str, str]] = set()
    for qualname in card.functions:
        for module, path in modules:
            if qualname.startswith(module + "."):
                keys.add((path, qualname.rsplit(".", 1)[-1]))
                break
    return keys


class CardHistory:
    """Kartların dosya ve fonksiyon bazında zaman sıralı dizini (`as_of` sorguları için)."""

    def __init__(self, cards: Iterable[BugCard]) -> None:
        by_file: dict[str, list[tuple[float, str]]] = {}
        by_func: dict[tuple[str, str], list[tuple[float, str]]] = {}
        for card in cards:
            t = card.fix_date.timestamp()
            for path in set(card.files):
                by_file.setdefault(path, []).append((t, card.id))
            for key in card_function_keys(card):
                by_func.setdefault(key, []).append((t, card.id))
        self._files = {k: sorted(v) for k, v in by_file.items()}
        self._funcs = {k: sorted(v) for k, v in by_func.items()}

    @staticmethod
    def _before(events: list[tuple[float, str]], as_of: float) -> list[str]:
        return [cid for _, cid in events[: bisect_left(events, (as_of, ""))]]

    def metrics(
        self, files: Iterable[str], functions: Iterable[tuple[str, str]], *, as_of: datetime
    ) -> dict[str, float]:
        t = as_of.timestamp()
        func_cards = {
            cid for key in set(functions) for cid in self._before(self._funcs.get(key, []), t)
        }
        file_cards = {
            cid for path in set(files) for cid in self._before(self._files.get(path, []), t)
        }
        return {"mem_func_bugs": float(len(func_cards)), "mem_file_bugs": float(len(file_cards))}
