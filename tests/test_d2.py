"""D2: hatalı commit'lerde beklenen satırlar ve temiz commit örneklemi (#51)."""

import json
from datetime import date
from pathlib import Path

import polars as pl
from typer.testing import CliRunner

from aegis.cli import app
from aegis.features import compute_kamei
from aegis.mining import mine_repository
from aegis.mining.d2 import build_d2, read_d2, sample_repo
from aegis.mining.dataset import build_d1
from aegis.mining.szz import blame_origins, run_szz
from tests.gitrepo import GitRepo

BASE = "def area(w, h):\n    return w * h\n\n\ndef perimeter(w, h):\n    return 2 * (w + h)\n"
BUGGY = BASE.replace("2 * (w + h)", "2 * w + h")


def _history(tmp_path: Path) -> tuple[GitRepo, dict[str, str], Path]:
    (tmp_path / "proj").mkdir()
    git = GitRepo(tmp_path / "proj")
    shas = {
        "init": git.commit("Add shapes", {"geo.py": BASE}, date="2023-01-01T10:00:00Z"),
        "clean": git.commit(
            "Add volume",
            {"geo.py": BASE + "\n\ndef volume(w, h, d):\n    return w * h * d\n"},
            date="2023-02-01T10:00:00Z",
        ),  # fmt: skip
        "bug": git.commit(
            "Simplify perimeter",
            {"geo.py": BUGGY + "\n\ndef volume(w, h, d):\n    return w * h * d\n"},
            date="2024-10-01T10:00:00Z",
        ),
        "fix": git.commit(
            "Fix perimeter formula",
            {"geo.py": BASE + "\n\ndef volume(w, h, d):\n    return w * h * d\n"},
            date="2024-11-01T10:00:00Z",
        ),
    }
    root = tmp_path / "data"
    mine_repository(git.path, root / "proj", slug="proj", functions=False)
    data = root / "proj"
    compute_kamei(
        pl.read_parquet(data / "commits.parquet"), pl.read_parquet(data / "files.parquet")
    ).write_parquet(data / "kamei.parquet")
    run_szz(git.path, data)
    build_d1(root, root / "d1.parquet", min_positives=0)
    return git, shas, root


def test_sample_repo_expected_lines(tmp_path: Path) -> None:
    git, shas, root = _history(tmp_path)
    d1 = pl.read_parquet(root / "d1.parquet")
    samples = sample_repo(
        git.path, root / "proj", d1, per_label=1, bins=1, min_added=1, clean_min_age_days=0
    )
    by_label = {s.label: s for s in samples}
    buggy, clean = by_label["buggy"], by_label["clean"]
    assert buggy.sha == shas["bug"] and buggy.fix_shas == [shas["fix"]]
    assert buggy.expected == [{"path": "geo.py", "line": 6}]  # "return 2 * w + h"
    assert "+    return 2 * w + h" in buggy.diff
    assert buggy.after_cutoff and buggy.parent == shas["clean"]
    assert clean.expected == [] and clean.label == "clean" and not clean.after_cutoff
    assert clean.sha in (shas["init"], shas["clean"])


def test_clean_commits_must_be_old_enough(tmp_path: Path) -> None:
    git, _, root = _history(tmp_path)
    d1 = pl.read_parquet(root / "d1.parquet")
    # En yeni commit 2024-11; 365 günden eski temiz commit var (2023), 1000 günden eski yok.
    old = sample_repo(git.path, root / "proj", d1, per_label=1, bins=1, min_added=1)
    assert {s.label for s in old} == {"buggy", "clean"}
    none = sample_repo(
        git.path, root / "proj", d1, per_label=1, bins=1, min_added=1, clean_min_age_days=1000
    )
    assert none == []  # temiz aday yoksa repo atlanır


def test_build_d2_and_cli(tmp_path: Path) -> None:
    git, _, root = _history(tmp_path)
    clones = tmp_path / "clones"
    clones.mkdir()
    git.path.rename(clones / "proj")
    out = tmp_path / "d2.jsonl"
    manifest = build_d2(
        root, clones, out, per_label=1, llm_cutoff=date(2024, 9, 1), bins=1, min_added=1
    )
    assert manifest["samples"] == len(read_d2(out)) and manifest["expected_lines"] >= 1
    assert json.loads(out.with_suffix(".json").read_text("utf-8"))["repos"]["proj"]["buggy"] <= 1

    result = CliRunner().invoke(
        app, ["dataset", "--level", "d2", "--data", str(root), "--out", str(tmp_path / "x.jsonl")]
    )
    assert result.exit_code == 0, result.output
    assert (
        "beklenen satır" in result.output
    )  # varsayılan ayarlarla bu küçük repoda örnek çıkmayabilir


def test_blame_origins_follow_renames(tmp_path: Path) -> None:
    (tmp_path / "r").mkdir()
    git = GitRepo(tmp_path / "r")
    wrote = git.commit("Add", {"old.py": "a = 1\nb = 2\n"}, date="2024-01-01T10:00:00Z")
    git.run("mv", "old.py", "new.py")
    git.run("commit", "-q", "-m", "Rename")
    edited = git.commit("Edit", {"new.py": "a = 1\nb = 3\n"}, date="2024-01-03T10:00:00Z")
    origins = blame_origins(git.path, "HEAD", "new.py", [1, 2], ignore_whitespace=True)
    assert origins == [(wrote, "old.py", 1), (edited, "new.py", 2)]
