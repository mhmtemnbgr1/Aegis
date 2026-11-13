"""Hibrit getirme (#25) ve tüm modlarda zamansal filtre (#26)."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from aegis.memory.cards import BugCard
from aegis.memory.index import build_index
from aegis.memory.retrieve import MemoryQuery, Retriever, query_from_range
from tests.gitrepo import GitRepo


def _card(n: int, day: int, files: list[str], funcs: list[str], text: str) -> BugCard:
    return BugCard(
        id=f"BC-{n:010d}",
        fix_sha=f"{n:040d}",
        fix_date=datetime(2024, 1, day, tzinfo=UTC),
        inducing_shas=[],
        issue=None,
        files=files,
        functions=funcs,
        message=text,
        before=text,
        after=text,
        fix_diff="",
        summary=text,
    )


CARDS = [
    _card(1, 1, ["app/pool.py"], ["app.pool.Pool.release"], "release pooled connection on timeout"),
    _card(2, 2, ["app/http.py"], ["app.http.decode"], "decode unicode response body"),
    _card(
        3, 3, ["app/pool.py"], ["app.pool.Pool.acquire"], "acquire waits forever when pool empty"
    ),
    _card(4, 4, ["app/bar.py"], ["app.bar.width"], "progress bar width wrong with ncols"),
    _card(5, 9, ["app/pool.py"], ["app.pool.Pool.release"], "release twice corrupts pool"),
]


@pytest.fixture(scope="module")
def retriever() -> Retriever:
    return Retriever(CARDS, build_index(CARDS, "lsa"))


def _q(**kw: object) -> MemoryQuery:
    base: dict[str, object] = {"files": [], "functions": [], "text": ""}
    return MemoryQuery(**{**base, **kw})  # type: ignore[arg-type]


def test_structural_prefers_same_function_then_recent(retriever: Retriever) -> None:
    q = _q(files=["app/pool.py"], functions=["app.pool.Pool.release"])
    ids = [h.card_id for h in retriever.search(q, k=5, mode="structural")]
    # Aynı fonksiyon (2+1 puan): kart 5 (yeni) ve 1; sonra yalnız aynı dosya: kart 3.
    assert ids == [CARDS[4].id, CARDS[0].id, CARDS[2].id]


def test_bm25_matches_terms(retriever: Retriever) -> None:
    hits = retriever.search(_q(text="unicode decode error in response"), k=2, mode="bm25")
    assert hits[0].card_id == CARDS[1].id
    assert hits[0].ranks == {"bm25": 1}


def test_hybrid_fuses_and_reports_ranks(retriever: Retriever) -> None:
    q = _q(files=["app/pool.py"], functions=["app.pool.Pool.release"], text="release connection")
    hits = retriever.search(q, k=3)
    assert hits[0].card_id in {CARDS[0].id, CARDS[4].id}
    assert set(hits[0].ranks) == {"structural", "bm25", "vector"}
    assert hits[0].score > hits[-1].score


@pytest.mark.parametrize("mode", ["hybrid", "structural", "bm25", "vector"])
def test_no_mode_returns_future_cards(retriever: Retriever, mode: str) -> None:
    before = datetime(2024, 1, 3, tzinfo=UTC)
    q = _q(
        files=["app/pool.py"],
        functions=["app.pool.Pool.release"],
        text="pool release",
        before=before,
    )
    hits = retriever.search(q, k=10, mode=mode)  # type: ignore[arg-type]
    assert hits and all(CARDS[int(h.card_id[3:]) - 1].fix_date < before for h in hits)


def test_empty_and_mismatched() -> None:
    assert Retriever([]).search(_q(text="x")) == []
    with pytest.raises(ValueError):
        Retriever(CARDS[:2], build_index(CARDS, "lsa"))
    assert Retriever(CARDS).search(_q(text="pool"), mode="vector") == []  # indeks yoksa boş


def test_query_from_range(tmp_path: Path) -> None:
    (tmp_path / "r").mkdir()
    git = GitRepo(tmp_path / "r")
    git.commit("Add", {"app/pool.py": "class Pool:\n    def release(self, c):\n        pass\n"})
    git.run("checkout", "-q", "-b", "pr")
    git.commit(
        "Change",
        {
            "app/pool.py": "class Pool:\n    def release(self, c):\n        self.free.append(c)\n",
            "tests/test_pool.py": "def test_x():\n    pass\n",
        },
        date="2024-02-01T00:00:00+00:00",
    )
    q = query_from_range(git.path, "main", "pr")
    assert q.files == ["app/pool.py"]
    assert q.functions == ["app.pool.Pool.release"]
    assert "self.free.append(c)" in q.text
