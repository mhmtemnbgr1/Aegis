"""Kamei metrikleri (#10) ve as_of zaman kuralı (#72).

Senaryo (tüm zamanlar UTC, commit zamanı):

    c0  2020-01-01  alice  pkg/a.py +100 (ADD), README.md +10 (ADD)
    c1  2021-01-01  bob    pkg/a.py +10 -5, pkg/sub/b.py +50 (ADD)
    c2  2022-01-01  alice  pkg/sub/b.py +5 -5

İncelenen değişiklik (alice, fix, as_of = 2022-07-02):

    pkg/a.py      +20 -10 (MODIFY)
    pkg/sub/b.py  +10  -0 (MODIFY)
    docs/x.md     +30     (ADD)
"""

import math
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import pytest

from aegis.features import KAMEI, Change, ChangeHistory, FileChange, compute_kamei, kamei_metrics
from aegis.features import kamei as k
from aegis.mining import mine_repository
from tests.gitrepo import GitRepo

T0 = datetime(2020, 1, 1, tzinfo=UTC)
T1 = datetime(2021, 1, 1, tzinfo=UTC)
T2 = datetime(2022, 1, 1, tzinfo=UTC)
AS_OF = datetime(2022, 7, 2, tzinfo=UTC)


def _history() -> ChangeHistory:
    h = ChangeHistory()
    h.add_commit(
        "c0",
        T0,
        "alice",
        [FileChange(None, "pkg/a.py", 100, 0), FileChange(None, "README.md", 10, 0)],
    )
    h.add_commit(
        "c1",
        T1,
        "bob",
        [FileChange("pkg/a.py", "pkg/a.py", 10, 5), FileChange(None, "pkg/sub/b.py", 50, 0)],
    )
    h.add_commit("c2", T2, "alice", [FileChange("pkg/sub/b.py", "pkg/sub/b.py", 5, 5)])
    return h


CHANGE = Change(
    developer="alice",
    files=[
        FileChange("pkg/a.py", "pkg/a.py", 20, 10),
        FileChange("pkg/sub/b.py", "pkg/sub/b.py", 10, 0),
        FileChange(None, "docs/x.md", 30, 0),
    ],
    is_fix=True,
)

# Elle hesaplanan beklenen değerler.
EXPECTED = {
    "ns": 2,  # {pkg, docs}
    "nd": 3,  # {pkg, pkg/sub, docs}
    "nf": 3,
    # Değişen satırlar 30, 10, 30 (toplam 70): −(2·3/7·log₂(3/7) + 1/7·log₂(1/7))
    "entropy": -(2 * 3 / 7 * math.log2(3 / 7) + 1 / 7 * math.log2(1 / 7)),  # ≈ 1.449
    "la": 60,  # 20 + 10 + 30
    "ld": 10,
    "lt": 155,  # a.py: 100 + 10 − 5 = 105; b.py: 50 + 5 − 5 = 50; x.md yeni
    "fix": 1,
    "ndev": 2,  # a.py {alice, bob} ∪ b.py {bob, alice}
    "age": (547 + 182) / 2,  # a.py son c1 → 547 gün; b.py son c2 → 182 gün
    "nuc": 3,  # a.py {c0, c1} ∪ b.py {c1, c2}
    "exp": 2,  # alice: c0, c2
    "rexp": 1 / 3 + 1 / 1,  # c0 2,5 yıl önce → 1/(2+1); c2 0,5 yıl önce → 1/(0+1)
    "sexp": 2,  # alice'in pkg'ye dokunduğu commit'ler: c0, c2 (docs'a hiç)
}


def test_fourteen_metrics_in_kamei_order() -> None:
    assert list(KAMEI) == [
        "ns", "nd", "nf", "entropy", "la", "ld", "lt",
        "fix", "ndev", "age", "nuc", "exp", "rexp", "sexp",
    ]  # fmt: skip


@pytest.mark.parametrize("name", list(EXPECTED))
def test_metric_hand_computed(name: str) -> None:
    value = KAMEI[name](CHANGE, _history(), as_of=AS_OF)
    assert value == pytest.approx(EXPECTED[name], abs=1e-9)


def test_kamei_metrics_dict() -> None:
    assert kamei_metrics(CHANGE, _history(), as_of=AS_OF) == pytest.approx(EXPECTED)


def test_entropy_edge_cases() -> None:
    h = ChangeHistory()
    single = Change("x", [FileChange("a.py", "a.py", 3, 2)])
    empty = Change("x", [FileChange("a.bin", "a.bin", 0, 0)])
    assert k.entropy(single, h, as_of=AS_OF) == 0
    assert k.entropy(empty, h, as_of=AS_OF) == 0


# as_of zaman kuralı (#72)


def test_event_at_as_of_is_invisible() -> None:
    h = _history()
    # Tam c2 anında sorgu: c2 görünmez (kesin önce kuralı).
    assert k.exp(CHANGE, h, as_of=T2) == 1
    assert h.line_count("pkg/sub/b.py", T2) == 50
    assert h.file_events("pkg/sub/b.py", T2)[1] == ["c1"]


def test_future_commits_do_not_change_features() -> None:
    before = kamei_metrics(CHANGE, _history(), as_of=AS_OF)
    h = _history()
    future = datetime(2023, 1, 1, tzinfo=UTC)
    h.add_commit(
        "c3",
        future,
        "carol",
        [FileChange("pkg/a.py", "pkg/a2.py", 7, 3), FileChange("docs/x.md", None, 0, 30)],
    )
    h.add_commit("c4", future.replace(month=2), "alice", [FileChange(None, "pkg/c.py", 9, 0)])
    assert kamei_metrics(CHANGE, h, as_of=AS_OF) == before


def test_rename_carries_history_forward_only() -> None:
    h = _history()
    renamed = datetime(2023, 1, 1, tzinfo=UTC)
    h.add_commit("c3", renamed, "carol", [FileChange("pkg/a.py", "pkg/a2.py", 1, 0)])
    later = datetime(2024, 1, 1, tzinfo=UTC)
    # Adlandırmadan sonra yeni yol, önceki yolun geçmişini taşır.
    assert h.file_events("pkg/a2.py", later)[1] == ["c0", "c1", "c3"]
    assert h.line_count("pkg/a2.py", later) == 106
    assert h.line_count("pkg/a.py", later) == 0
    # Adlandırmadan önce yeni yolun geçmişi yok, eski yolunki değişmemiş.
    assert h.file_events("pkg/a2.py", renamed)[1] == []
    assert h.file_events("pkg/a.py", renamed)[1] == ["c0", "c1"]


def test_out_of_order_commits_rejected() -> None:
    h = _history()
    with pytest.raises(ValueError, match="sıralı"):
        h.add_commit("old", T0, "x", [])


# Madencilik çıktısı üzerinde uçtan uca


def _mined_repo(tmp_path: Path, *, with_future: bool) -> pl.DataFrame:
    path = tmp_path / ("future" if with_future else "base")
    path.mkdir()
    git = GitRepo(path)
    git.commit("Add a", {"pkg/a.py": "x = 1\n" * 4}, date="2024-01-01T00:00:00+00:00")
    git.commit("Grow a", {"pkg/a.py": "x = 1\n" * 6}, date="2024-02-01T00:00:00+00:00")
    git.commit(
        "Fix a", {"pkg/a.py": "x = 2\n" * 6}, date="2024-03-01T00:00:00+00:00",
        author=("Ayse", "AYSE@example.com"),
    )  # fmt: skip
    if with_future:
        git.commit(
            "Rewrite a",
            {"pkg/a.py": "y = 0\n", "pkg/b.py": "z\n"},
            date="2025-01-01T00:00:00+00:00",
        )
    out = tmp_path / ("out-future" if with_future else "out-base")
    mine_repository(git.path, out, functions=False)
    return compute_kamei(
        pl.read_parquet(out / "commits.parquet"), pl.read_parquet(out / "files.parquet")
    )


def test_compute_kamei_on_mined_repo(tmp_path: Path) -> None:
    features = _mined_repo(tmp_path, with_future=False)
    assert features.columns == ["repo", "sha", "as_of", *KAMEI]
    assert features.height == 3
    fix_row = features.row(2, named=True)
    # Fix commit'i: 6 satır değişti; önceki iki commit "Dev" tarafından yapıldı.
    assert (fix_row["la"], fix_row["ld"], fix_row["lt"]) == (6, 6, 6)
    assert (fix_row["fix"], fix_row["nuc"], fix_row["ndev"], fix_row["exp"]) == (1, 2, 1, 0)
    assert fix_row["age"] == pytest.approx(29)  # 1 Şubat → 1 Mart 2024


def test_future_commit_leaves_mined_features_unchanged(tmp_path: Path) -> None:
    base = _mined_repo(tmp_path, with_future=False)
    future = _mined_repo(tmp_path, with_future=True)
    assert future.height == base.height + 1
    shared = future.drop("repo", "sha").head(base.height)
    assert shared.equals(base.drop("repo", "sha"))
