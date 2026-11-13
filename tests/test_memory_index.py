"""Embedding ve vektör indeksi (#24), zamansal filtre (#26)."""

import pickle
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from aegis.memory.cards import BugCard
from aegis.memory.embed import LsaEmbedder, OllamaEmbedder, code_tokens, create_embedder
from aegis.memory.index import MemoryIndex, build_index, card_text


def _card(n: int, summary: str, code: str, day: int) -> BugCard:
    return BugCard(
        id=f"BC-{n:010d}",
        fix_sha=f"{n:040d}",
        fix_date=datetime(2024, 1, day, tzinfo=UTC),
        inducing_shas=[],
        issue=None,
        files=["app/x.py"],
        functions=[],
        message=summary,
        before=code,
        after=code,
        fix_diff="",
        summary=summary,
    )


_SPECS = [
    ("Release pooled connection on timeout", "def release(self, conn):\n    pool.put(conn)"),
    ("Fix unicode decode of response body", "def decode(body):\n    return body.decode()"),
    ("Close connection pool on shutdown", "def shutdown(self):\n    self.pool.close_all()"),
    ("Fix progress bar width with ncols", "def bar_width(ncols):\n    return ncols - 2"),
    ("Fix retry of failed http request", "def retry(request):\n    return send(request)"),
]
CARDS = [_card(i, s, c, i) for i, (s, c) in enumerate(_SPECS, 1)]


def test_code_tokens() -> None:
    assert code_tokens("release_conn getAttr x") == [
        "release", "conn", "release_conn", "get", "attr", "getattr",
    ]  # fmt: skip


def test_lsa_finds_related_card() -> None:
    index = build_index(CARDS, "lsa")
    hits = index.search("connection pool leak when releasing conn", k=2)
    assert {h.card_id for h in hits} == {CARDS[0].id, CARDS[2].id}
    vectors = index.vectors
    assert vectors.dtype == np.float32
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=1e-5)


def test_future_cards_are_never_returned() -> None:
    index = build_index(CARDS, "lsa")
    cutoff = datetime(2024, 1, 3, tzinfo=UTC)
    hits = index.search("connection pool", k=5, before=cutoff)
    assert {h.card_id for h in hits} == {CARDS[0].id, CARDS[1].id}  # 3. gün dahil değil
    assert index.search("anything", before=datetime(2023, 1, 1, tzinfo=UTC)) == []


def test_save_load_roundtrip(tmp_path: Path) -> None:
    index = build_index(CARDS, "lsa")
    index.save(tmp_path / "idx", "abc")
    loaded = MemoryIndex.load(tmp_path / "idx")
    assert loaded.ids == index.ids
    assert np.allclose(loaded.vectors, index.vectors)
    assert loaded.search("unicode decode", k=1)[0].card_id == CARDS[1].id
    assert '"cards_sha256": "abc"' in (tmp_path / "idx" / "index.json").read_text("utf-8")


def test_tiny_and_empty_indexes() -> None:
    one = build_index(CARDS[:1], "lsa")
    assert one.search("release", k=3)[0].card_id == CARDS[0].id
    assert build_index([], "lsa").search("x") == []


def test_create_embedder() -> None:
    assert isinstance(create_embedder("local"), LsaEmbedder)
    assert create_embedder("lsa:64").dims == 64  # type: ignore[attr-defined]
    assert create_embedder("ollama:nomic-embed-text").name == "ollama:nomic-embed-text"
    with pytest.raises(ValueError):
        create_embedder("bert")


def test_ollama_embedder_with_fake_client() -> None:
    class Client:
        calls = 0

        def embed(self, model: str, input: list[str]) -> dict[str, list[list[float]]]:
            Client.calls += 1
            return {"embeddings": [[float(len(t)), 1.0] for t in input]}

    emb = OllamaEmbedder("m", client=Client(), batch=2)
    vectors = emb.fit(["a", "bb", "ccc"]).encode(["a", "bb", "ccc"])
    assert vectors.shape == (3, 2) and Client.calls == 2
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0)
    restored = pickle.loads(pickle.dumps(emb))
    assert restored._client is None  # ağ istemcisi diske yazılmaz


def test_card_text_includes_code_and_functions() -> None:
    text = card_text(CARDS[0].model_copy(update={"functions": ["app.x.release"]}))
    assert "app.x.release" in text and "pool.put(conn)" in text
