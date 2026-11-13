"""Hafıza sinyali: geçmiş hata kartı sayısı (#29)."""

from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from aegis.config import AegisConfig
from aegis.features.kamei import compute_kamei
from aegis.features.memory import CardHistory, card_function_keys
from aegis.gatekeeper.score import range_commits
from aegis.memory.cards import BugCard, build_cards, write_cards
from aegis.mining import mine_repository
from aegis.mining.dataset import build_repo
from aegis.mining.szz import run_szz
from tests.gitrepo import GitRepo


def _card(n: int, day: int, files: list[str], funcs: list[str]) -> BugCard:
    return BugCard(
        id=f"BC-{n:010d}",
        fix_sha=f"{n:040d}",
        fix_date=datetime(2024, 1, day, tzinfo=UTC),
        inducing_shas=[],
        issue=None,
        files=files,
        functions=funcs,
        message="",
        before="",
        after="",
        fix_diff="",
        summary="",
    )


def test_card_function_keys_use_file_and_short_name() -> None:
    card = _card(
        1, 1, ["app/pool.py", "app/db/__init__.py"], ["app.pool.Pool.release", "app.db.connect"]
    )
    assert card_function_keys(card) == {
        ("app/pool.py", "release"),
        ("app/db/__init__.py", "connect"),
    }


def test_counts_only_earlier_cards_and_future_cards_change_nothing() -> None:
    cards = [
        _card(1, 1, ["app/pool.py"], ["app.pool.Pool.release"]),
        _card(2, 2, ["app/pool.py"], ["app.pool.Pool.acquire"]),
        _card(3, 5, ["app/pool.py"], ["app.pool.Pool.release"]),
    ]
    as_of = datetime(2024, 1, 5, tzinfo=UTC)  # kart 3 ile aynı an: sayılmaz (kesin küçük)
    files, funcs = ["app/pool.py"], [("app/pool.py", "release")]
    value = CardHistory(cards).metrics(files, funcs, as_of=as_of)
    assert value == {"mem_func_bugs": 1.0, "mem_file_bugs": 2.0}
    future = _card(4, 20, ["app/pool.py"], ["app.pool.Pool.release"])
    assert CardHistory([*cards, future]).metrics(files, funcs, as_of=as_of) == value
    assert CardHistory([]).metrics(files, funcs, as_of=as_of) == {
        "mem_func_bugs": 0.0,
        "mem_file_bugs": 0.0,
    }


POOL = (
    "class Pool:\n"
    "    def release(self, c):\n"
    "        return {}\n"
    "\n"
    "    def size(self):\n"
    "        return 0\n"
)


def test_d1_and_runtime_get_memory_signal(tmp_path: Path) -> None:
    (tmp_path / "p").mkdir()
    git = GitRepo(tmp_path / "p")
    git.commit("Add pool", {"app/pool.py": POOL.format("1")}, date="2024-01-01T00:00:00+00:00")
    git.commit(
        "Fix release crash",
        {"app/pool.py": POOL.replace("{}", "2")},
        date="2024-02-01T00:00:00+00:00",
    )
    git.commit(
        "Tweak release", {"app/pool.py": POOL.replace("{}", "3")}, date="2024-03-01T00:00:00+00:00"
    )
    data = tmp_path / "data"
    mine_repository(git.path, data)
    run_szz(git.path, data)
    commits = pl.read_parquet(data / "commits.parquet")
    compute_kamei(commits, pl.read_parquet(data / "files.parquet")).write_parquet(
        data / "kamei.parquet"
    )
    write_cards(data / "cards.jsonl", build_cards(git.path, data))
    rows, _ = build_repo(data)
    by_msg = dict(zip(commits["sha"], commits["message"], strict=True))
    values = {
        by_msg[s].strip(): (f, g)
        for s, f, g in rows.select("sha", "mem_func_bugs", "mem_file_bugs").iter_rows()
    }
    assert values["Fix release crash"] == (0.0, 0.0)  # kendi kartını görmez
    assert values["Tweak release"] == (1.0, 1.0)

    [last] = range_commits(git.path, "HEAD~1", "HEAD", AegisConfig())
    assert last.functions == (("app/pool.py", "release"),)
