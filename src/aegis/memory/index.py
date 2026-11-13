"""Hata kartlarının vektör indeksi: numpy dosyaları, tam tarama (#24, #26).

İndeks repo başına `<index_path>/<repo>/` dizinindedir:

- `vectors.npy`: kart vektörleri (L2 normalize, float32),
- `embedder.pkl`: eğitilmiş embedding modeli (LSA) ya da ayarları (Ollama),
- `index.json`: sürüm kaydı — şema, Aegis sürümü, embedding modeli, kart sayısı, kartların
  özeti (SHA-256), kart kimlikleri ve fix tarihleri.

Arama tam taramadır (kosinüs benzerliği = iç çarpım). Birkaç bin kart için milisaniyeler sürer;
LanceDB gibi bir vektör veritabanına bu ölçekte gerek yoktur.

**Zamansal filtre (FR-23):** `before` verildiğinde yalnızca `fix_date < before` olan kartlar döner;
değerlendirmede de aynı kural geçerlidir.
"""

import hashlib
import json
import pickle
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from aegis import __version__
from aegis.memory.cards import BugCard
from aegis.memory.embed import Embedder, Matrix, create_embedder

SCHEMA_VERSION = 1


def card_text(card: BugCard) -> str:
    """Embedding için kart metni: özet, mesaj, dosyalar, fonksiyonlar, kod ve diff."""
    return "\n".join(
        [
            card.summary,
            card.message,
            " ".join(card.files),
            " ".join(card.functions),
            card.before,
            card.after,
            card.fix_diff,
        ]
    )


@dataclass(frozen=True)
class Hit:
    card_id: str
    score: float


class MemoryIndex:
    def __init__(
        self, embedder: Embedder, vectors: Matrix, ids: list[str], dates: list[datetime]
    ) -> None:
        self.embedder = embedder
        self.vectors = vectors
        self.ids = ids
        self.dates = np.array([d.timestamp() for d in dates], dtype=np.float64)

    @classmethod
    def build(cls, cards: list[BugCard], embedder: Embedder) -> "MemoryIndex":
        texts = [card_text(c) for c in cards]
        vectors = embedder.fit(texts).encode(texts) if cards else np.zeros((0, 1), np.float32)
        return cls(embedder, vectors, [c.id for c in cards], [c.fix_date for c in cards])

    def search(self, query: str, k: int = 3, before: datetime | None = None) -> list[Hit]:
        """En benzer `k` kart; `before` verilirse yalnızca ondan önce düzeltilmiş olanlar."""
        if not self.ids:
            return []
        scores = self.vectors @ self.embedder.encode([query])[0]
        if before is not None:
            scores = np.where(self.dates < before.timestamp(), scores, -np.inf)
        order = np.argsort(-scores, kind="stable")[:k]
        return [Hit(self.ids[i], float(scores[i])) for i in order if np.isfinite(scores[i])]

    def save(self, directory: Path, cards_digest: str) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        np.save(directory / "vectors.npy", self.vectors)
        with (directory / "embedder.pkl").open("wb") as fh:
            pickle.dump(self.embedder, fh)
        manifest: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "aegis_version": __version__,
            "built_at": datetime.now(UTC).isoformat(),
            "embedder": self.embedder.name,
            "cards": len(self.ids),
            "cards_sha256": cards_digest,
            "ids": self.ids,
            "fix_dates": [datetime.fromtimestamp(t, UTC).isoformat() for t in self.dates],
        }
        (directory / "index.json").write_text(json.dumps(manifest, indent=1), "utf-8")

    @classmethod
    def load(cls, directory: Path) -> "MemoryIndex":
        manifest = json.loads((directory / "index.json").read_text("utf-8"))
        if manifest.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(f"{directory}: desteklenmeyen indeks sürümü")
        with (directory / "embedder.pkl").open("rb") as fh:
            embedder = pickle.load(fh)  # nosec B301: yalnızca kendi ürettiğimiz dosyalar
        vectors = np.load(directory / "vectors.npy")
        dates = [datetime.fromisoformat(d) for d in manifest["fix_dates"]]
        return cls(embedder, vectors, list(manifest["ids"]), dates)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""


def build_index(cards: list[BugCard], spec: str) -> MemoryIndex:
    return MemoryIndex.build(cards, create_embedder(spec))
