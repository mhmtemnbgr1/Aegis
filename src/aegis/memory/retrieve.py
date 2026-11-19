"""Hibrit getirme: yapısal + BM25 + vektör, Reciprocal Rank Fusion (FR-22, #25).

Sorgu, incelenen değişikliğin (PR ya da commit aralığı) dosyaları, değiştirdiği fonksiyonların
nitelikli adları ve metnidir (fonksiyon kodu + diff). Üç sıralama üretilir:

- **yapısal:** aynı fonksiyon (2 puan) ve aynı dosya (1 puan) eşleşmesi, kartın fonksiyon ve dosya
  sayısına bölünerek; eşitlikte yeni kart önce,
- **BM25:** kart metni üzerinde Okapi BM25 (k1 = 1,2, b = 0,75), kod duyarlı belirteçlerle,
- **vektör:** embedding indeksinde kosinüs benzerliği (bkz. `index`).

`hybrid` modu üç sıralamayı RRF ile birleştirir: puan = Σ 1 / (60 + sıra). Her yöntemden yalnızca
ilk `depth` kart birleştirmeye girer. **Zamansal filtre (FR-23)** her yönteme ayrı ayrı uygulanır:
`fix_date < before` olmayan kart hiçbir moddan dönmez.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np
from numpy.typing import NDArray

from aegis.config import AegisConfig
from aegis.memory.cards import BugCard, read_cards
from aegis.memory.chunk import changed_lines, functions, touched
from aegis.memory.embed import code_tokens
from aegis.memory.index import MemoryIndex, card_text
from aegis.mining.gitfiles import git, tree_changes

Mode = Literal["hybrid", "vector", "structural", "bm25"]
RRF_K = 60


@dataclass(frozen=True)
class MemoryQuery:
    files: list[str]
    functions: list[str]
    text: str
    before: datetime | None = None


@dataclass
class RetrievalHit:
    card_id: str
    score: float
    ranks: dict[str, int] = field(default_factory=dict)
    """Yöntem → bu kartın o yöntemdeki sırası (1 tabanlı); açıklama ve ablasyon için."""


def query_from_range(
    repo: Path,
    base: str,
    head: str,
    config: AegisConfig | None = None,
    before: datetime | None = None,
) -> MemoryQuery:
    """`base..head` aralığından sorgu: değişen kaynak dosyaları, fonksiyonlar, kod ve diff."""
    return _query(repo, base, head, config, before, use_merge_base=True)


def query_from_diff(
    repo: Path,
    old: str,
    new: str,
    config: AegisConfig | None = None,
    before: datetime | None = None,
) -> MemoryQuery:
    """`old` → `new` değişikliğinden sorgu; ortak ata aranmaz.

    D2'deki tersine çevrilmiş düzeltmeler için (`old` = fix, `new` = fix'in ebeveyni): diff,
    düzeltilmiş koddan hatalı koda giden değişikliktir.
    """
    return _query(repo, old, new, config, before, use_merge_base=False)


def _query(
    repo: Path,
    base: str,
    head: str,
    config: AegisConfig | None,
    before: datetime | None,
    *,
    use_merge_base: bool,
) -> MemoryQuery:
    """`base..head` aralığından sorgu: değişen kaynak dosyaları, fonksiyonlar, kod ve diff."""
    import re

    config = config or AegisConfig()
    mining, mem = config.mining, config.memory
    tests = [re.compile(p) for p in mining.test_path_patterns]
    merge_base = git(repo, "merge-base", base, head).strip() if use_merge_base else base
    paths = [
        f.path
        for f in tree_changes(repo, merge_base, head)
        if f.new_path
        and f.path.endswith(tuple(mining.source_extensions))
        and not any(t.search(f.path) for t in tests)
    ]
    names: list[str] = []
    code: list[str] = []
    for path in paths:
        _, new_lines = changed_lines(git(repo, "diff", "-U0", merge_base, head, "--", path))
        source = git(repo, "show", f"{head}:{path}")
        for span in touched(functions(source, path), new_lines):
            names.append(span.qualname)
            code.append("\n".join(source.splitlines()[span.start - 1 : span.end]))
    diff = git(repo, "diff", "-U3", merge_base, head, "--", *paths).splitlines() if paths else []
    text = "\n".join([*names, *code, *diff[: mem.max_diff_lines * 4]])
    return MemoryQuery(files=paths, functions=names, text=text, before=before)


class Retriever:
    def __init__(self, cards: list[BugCard], index: MemoryIndex | None = None) -> None:
        from sklearn.feature_extraction.text import CountVectorizer

        self.cards = cards
        self.index = index
        self.dates = np.array([c.fix_date.timestamp() for c in cards], dtype=np.float64)
        if index is not None and index.ids != [c.id for c in cards]:
            raise ValueError("indeks ile kartlar uyuşmuyor; aegis index ile yeniden kurun")
        self._by_function: dict[str, list[int]] = {}
        self._by_file: dict[str, list[int]] = {}
        for i, c in enumerate(cards):
            for name in c.functions:
                self._by_function.setdefault(name, []).append(i)
            for path in c.files:
                self._by_file.setdefault(path, []).append(i)
        self._counts: Any = None
        if cards:
            self._vectorizer = CountVectorizer(
                tokenizer=code_tokens, token_pattern=None, lowercase=False
            )
            self._counts = self._vectorizer.fit_transform([card_text(c) for c in cards]).tocsc()
            lengths = np.asarray(self._counts.sum(axis=1)).ravel()
            self._norm = 1.2 * (0.25 + 0.75 * lengths / max(lengths.mean(), 1.0))
            df = np.asarray((self._counts > 0).sum(axis=0)).ravel()
            self._idf = np.log(1 + (len(cards) - df + 0.5) / (df + 0.5))

    @classmethod
    def load(cls, cards_path: Path, index_dir: Path | None = None) -> "Retriever":
        index = MemoryIndex.load(index_dir) if index_dir and index_dir.is_dir() else None
        return cls(read_cards(cards_path), index)

    def _allowed(self, before: datetime | None) -> NDArray[np.bool_]:
        if before is None:
            return np.ones(len(self.cards), dtype=bool)
        return self.dates < before.timestamp()

    def _rank(self, scores: NDArray[np.float64], allowed: NDArray[np.bool_]) -> list[int]:
        """Puanı > 0 ve izinli kartlar; puana, eşitlikte yeni fix'e göre azalan."""
        keep = np.flatnonzero(allowed & (scores > 0))
        order = np.lexsort((-self.dates[keep], -scores[keep]))
        return [int(i) for i in keep[order]]

    def structural(self, query: MemoryQuery) -> list[int]:
        """Aynı fonksiyon 2, aynı dosya 1 puan; kartın genişliğine bölünür.

        Çok dosyaya dokunan toplu commit'ler (ör. "fix linkcheck", "docstring fixes") yalnızca
        aynı dosyayı da değiştirdikleri için üste çıkmasın diye her eşleşme, kartın fonksiyon ya da
        dosya sayısına bölünür.
        """
        scores = np.zeros(len(self.cards))
        for name in set(query.functions):
            for i in self._by_function.get(name, []):
                scores[i] += 2 / len(self.cards[i].functions)
        for path in set(query.files):
            for i in self._by_file.get(path, []):
                scores[i] += 1 / len(self.cards[i].files)
        return self._rank(scores, self._allowed(query.before))

    def bm25(self, query: MemoryQuery) -> list[int]:
        if self._counts is None:
            return []
        vocab = self._vectorizer.vocabulary_
        terms = {vocab[t] for t in code_tokens(query.text) if t in vocab}
        scores = np.zeros(len(self.cards))
        for j in terms:
            col = self._counts.getcol(j)
            rows, tf = col.indices, col.data.astype(np.float64)
            scores[rows] += self._idf[j] * tf * 2.2 / (tf + self._norm[rows])
        return self._rank(scores, self._allowed(query.before))

    def vector(self, query: MemoryQuery) -> list[int]:
        if self.index is None or not self.cards:
            return []
        sims = self.index.vectors @ self.index.embedder.encode([query.text])[0]
        return self._rank(sims.astype(np.float64), self._allowed(query.before))

    def search(
        self, query: MemoryQuery, k: int = 3, mode: Mode = "hybrid", depth: int = 50
    ) -> list[RetrievalHit]:
        if not self.cards:
            return []
        if mode != "hybrid":
            ranked = getattr(self, mode)(query)[:k]
            return [
                RetrievalHit(self.cards[i].id, 1.0 / (RRF_K + r), {mode: r})
                for r, i in enumerate(ranked, 1)
            ]
        fused: dict[int, RetrievalHit] = {}
        for name in ("structural", "bm25", "vector"):
            for r, i in enumerate(getattr(self, name)(query)[:depth], 1):
                hit = fused.setdefault(i, RetrievalHit(self.cards[i].id, 0.0))
                hit.score += 1.0 / (RRF_K + r)
                hit.ranks[name] = r
        order = sorted(fused, key=lambda i: (-fused[i].score, -self.dates[i]))
        return [fused[i] for i in order[:k]]

    def card(self, card_id: str) -> BugCard:
        return next(c for c in self.cards if c.id == card_id)
