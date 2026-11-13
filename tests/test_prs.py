"""PR düzeyinde D1: eşleme, etiket ve yasaklı özellikler (#73)."""

from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from aegis.features.kamei import KAMEI, compute_kamei
from aegis.mining import mine_repository
from aegis.mining.prs import FORBIDDEN, PR_FEATURES, build_pr_rows, find_prs
from tests.gitrepo import GitRepo


def _merge(git: GitRepo, branch: str, message: str, date: str) -> str:
    env = {"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
    git.run("merge", "--no-ff", "-q", "-m", message, branch, env=env)
    return git.run("rev-parse", "HEAD")


def _build(tmp_path: Path, *, merge_date: str, later: bool) -> tuple[GitRepo, pl.DataFrame]:
    """main'de 2 commit; 2 yazarlı bir merge PR'ı (#5); bir squash PR'ı (#6)."""
    root = tmp_path / ("later" if later else "base") / merge_date[:10]
    root.mkdir(parents=True)
    git = GitRepo(root)
    git.commit("Add core", {"pkg/core.py": "a = 1\n"}, date="2024-01-01T00:00:00+00:00")
    git.commit("Add util", {"pkg/util.py": "u = 1\n"}, date="2024-01-02T00:00:00+00:00")
    git.run("checkout", "-q", "-b", "feature")
    git.commit("Change core", {"pkg/core.py": "a = 2\nb = 1\n"}, date="2024-02-01T00:00:00+00:00")
    git.commit(
        "Add api",
        {"pkg/api.py": "x = 1\ny = 2\n"},
        date="2024-02-02T00:00:00+00:00",
        author=("Other", "other@example.com"),
    )
    git.run("checkout", "-q", "main")
    _merge(git, "feature", "Merge pull request #5 from dev/feature\n\nCore", merge_date)
    git.commit("Fix util crash (#6)", {"pkg/util.py": "u = 2\n"}, date="2024-04-01T00:00:00+00:00")
    if later:  # PR'lardan sonra gelen ve onlara dokunan bir commit
        git.commit(
            "Touch core", {"pkg/core.py": "a = 3\nb = 1\n"}, date="2024-05-01T00:00:00+00:00"
        )
    data = tmp_path / "data" / root.parent.name / root.name
    mine_repository(git.path, data, functions=False)
    commits = pl.read_parquet(data / "commits.parquet")
    kamei = compute_kamei(commits, pl.read_parquet(data / "files.parquet"))
    change_core = commits.filter(pl.col("message").str.starts_with("Change core"))["sha"][0]
    d1 = kamei.with_columns(
        (pl.col("sha") == change_core).alias("buggy"),
        pl.when(pl.col("sha") == change_core)
        .then(pl.lit(datetime(2024, 6, 1, tzinfo=UTC)))
        .otherwise(None)
        .cast(pl.Datetime("us", "UTC"))
        .alias("fixed_at"),
    )
    return git, build_pr_rows(git.path, data, d1)


def test_find_prs(tmp_path: Path) -> None:
    git, _ = _build(tmp_path, merge_date="2024-03-01T00:00:00+00:00", later=False)
    prs = find_prs(git.path)
    assert [(p.number, p.style, len(p.commits)) for p in prs] == [(5, "merge", 2), (6, "squash", 1)]


def test_pr_rows_labels_and_features(tmp_path: Path) -> None:
    _, rows = _build(tmp_path, merge_date="2024-03-01T00:00:00+00:00", later=False)
    merge, squash = rows.to_dicts()
    assert (merge["pr"], merge["style"], squash["pr"], squash["style"]) == (5, "merge", 6, "squash")
    # Etiket: PR'ın commit'lerinden biri hatalı → PR hatalı; fixed_at onun düzeltme anı.
    assert merge["buggy"] and merge["fixed_at"] == datetime(2024, 6, 1, tzinfo=UTC)
    assert not squash["buggy"] and squash["fixed_at"] is None
    # Birleşik diff: core.py (+2 −1) ve api.py (+2); iki commit, iki yazar.
    assert (merge["la"], merge["ld"], merge["nf"]) == (4, 1, 2)
    assert (merge["n_commits"], merge["n_authors"]) == (2, 2)
    # as_of = PR'ın ilk commit'i; geçmişte yalnızca main'deki 2 commit görünür.
    assert merge["as_of"] == datetime(2024, 2, 1, tzinfo=UTC)
    assert merge["nuc"] == 1  # core.py bir kez değişmiş (PR'ın kendi commit'i sayılmaz)
    assert (squash["n_commits"], squash["fix"]) == (1, 1)
    assert len(merge["commits"]) == 2 and squash["commits"] == [squash["sha"]]


def test_no_post_hoc_information(tmp_path: Path) -> None:
    """Merge zamanı ya da PR'dan sonraki commit'ler özellikleri değiştirmez."""
    _, base = _build(tmp_path, merge_date="2024-03-01T00:00:00+00:00", later=False)
    _, late_merge = _build(tmp_path, merge_date="2024-03-25T00:00:00+00:00", later=True)
    for col in ("as_of", *PR_FEATURES):
        assert base[col].to_list() == late_merge[col].to_list(), col
    assert not FORBIDDEN & set(base.columns)
    assert set(PR_FEATURES) - set(KAMEI) == {"n_commits", "n_authors"}


def test_pr_model_uses_pr_features() -> None:
    from aegis.config import TrainingConfig
    from aegis.gatekeeper.model import train_model
    from aegis.gatekeeper.split import time_split
    from tests.test_gk_model import _d1

    rows = _d1(400, seed=6).with_columns(
        pl.lit(2.0).alias("n_commits"), pl.lit(1.0).alias("n_authors")
    )
    model = train_model(
        time_split(rows, TrainingConfig(label_delay_days=14)), "lr", features=PR_FEATURES
    )
    assert model.features == PR_FEATURES and model.meta["features"] == list(PR_FEATURES)
    assert len(model.explain_pr(rows.tail(3))) <= 3
