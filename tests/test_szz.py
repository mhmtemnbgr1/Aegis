"""SZZ, geçmişi bilinen sentetik depolarda doğru inducing commit'i buluyor mu (#9, #12)."""

import json
from pathlib import Path

import polars as pl
import pytest

from aegis.config import MiningConfig
from aegis.mining import mine_repository, schema
from aegis.mining.szz import blame_lines, deleted_lines, run_szz
from tests.gitrepo import GitRepo

V1 = "# sums values\ndef total(xs):\n    s = 0\n    for x in xs:\n        s += x\n    return s\n"
BUGGY = V1.replace("return s\n", "return s + 1\n")
REFORMATTED = V1.replace("return s\n", "return s+1\n")  # yalnız boşluk değişikliği
FIXED = V1.replace("# sums values\n", "")


@pytest.fixture
def repo(tmp_path: Path) -> tuple[GitRepo, dict[str, str]]:
    (tmp_path / "proj").mkdir()
    git = GitRepo(tmp_path / "proj")
    shas = {
        "init": git.commit("Add total", {"app.py": V1}, date="2024-01-01T10:00:00+00:00"),
        "bug": git.commit(
            "Count the header row", {"app.py": BUGGY}, date="2024-01-02T10:00:00+00:00"
        ),
        "ws": git.commit("Tidy spacing", {"app.py": REFORMATTED}, date="2024-01-03T10:00:00+00:00"),
        "testfix": git.commit(
            "Fix flaky test",
            {"tests/test_app.py": "def test_x():\n    assert True\n"},
            date="2024-01-04T10:00:00+00:00",
        ),
        "fix": git.commit(
            "Fix off-by-one in total", {"app.py": FIXED}, date="2024-01-05T10:00:00+00:00"
        ),
    }
    return git, shas


def _szz(git: GitRepo, out: Path, **config: object) -> pl.DataFrame:
    cfg = MiningConfig.model_validate(config)
    mine_repository(git.path, out, cfg, slug="proj", functions=False)
    run_szz(git.path, out, cfg)
    return pl.read_parquet(out / "szz.parquet")


def test_ma_finds_inducing_commit(repo: tuple[GitRepo, dict[str, str]], tmp_path: Path) -> None:
    git, shas = repo
    pairs = _szz(git, tmp_path / "out", szz_variant="ma")
    assert pairs.schema == pl.Schema(schema.SZZ)
    # Boşluk değişikliği (ws) ve silinen yorum satırı (init) yok sayılır.
    assert pairs.select("fix_sha", "inducing_sha", "path", "blamed_lines").rows() == [
        (shas["fix"], shas["bug"], "app.py", 1)
    ]
    meta = json.loads((tmp_path / "out" / "szz_meta.json").read_text("utf-8"))
    assert meta["variant"] == "ma"
    assert meta["fixes_in_window"] == 2
    assert meta["fixes_without_source"] == 1  # yalnız test dosyasına dokunan fix
    assert meta["fixes_with_inducing"] == 1


def test_b_blames_plainly(repo: tuple[GitRepo, dict[str, str]], tmp_path: Path) -> None:
    git, shas = repo
    pairs = _szz(git, tmp_path / "out", szz_variant="b")
    assert set(pairs["inducing_sha"]) == {shas["ws"], shas["init"]}
    meta = json.loads((tmp_path / "out" / "szz_meta.json").read_text("utf-8"))
    assert meta["variant"] == "b"


def test_ma_skips_mass_changes(tmp_path: Path) -> None:
    (tmp_path / "p").mkdir()
    git = GitRepo(tmp_path / "p")
    git.commit("Add", {"a.py": "x = 1\n", "b.py": "y = 1\n", "c.py": "z = 1\n"})
    bug = git.commit("Change a", {"a.py": "x = 2\n"}, date="2024-01-02T00:00:00+00:00")
    mass = git.commit(
        "Reformat everything",
        {"a.py": "x = (2)\n", "b.py": "y = (1)\n", "c.py": "z = (1)\n"},
        date="2024-01-03T00:00:00+00:00",
    )
    fix = git.commit("Fix x", {"a.py": "x = 1\n"}, date="2024-01-04T00:00:00+00:00")

    ma = _szz(git, tmp_path / "ma", szz_variant="ma", max_files_per_commit=2)
    assert ma.select("fix_sha", "inducing_sha").rows() == [(fix, bug)]
    b = _szz(git, tmp_path / "b", szz_variant="b", max_files_per_commit=2)
    assert b.select("fix_sha", "inducing_sha").rows() == [(fix, mass)]


def test_history_window_and_large_fixes(tmp_path: Path) -> None:
    (tmp_path / "p").mkdir()
    git = GitRepo(tmp_path / "p")
    git.commit("Add", {"a.py": "x = 1\n"}, date="2020-01-01T00:00:00+00:00")
    git.commit("Fix old bug", {"a.py": "x = 2\n"}, date="2020-02-01T00:00:00+00:00")
    git.commit(
        "Fix everything at once",
        {f"m{i}.py": "v = 1\n" for i in range(3)},
        date="2025-12-01T00:00:00+00:00",
    )
    git.commit("Update readme", {"README.md": "x\n"}, date="2026-01-01T00:00:00+00:00")
    cfg = MiningConfig(history_years=1, max_files_per_commit=2)
    mine_repository(git.path, tmp_path / "o", cfg, functions=False)
    result = run_szz(git.path, tmp_path / "o", cfg)
    assert (result.fixes_in_window, result.fixes_skipped_large, result.pairs) == (1, 1, 0)


def test_deleted_lines_and_blame(repo: tuple[GitRepo, dict[str, str]]) -> None:
    git, shas = repo
    parent = shas["testfix"]
    plain = deleted_lines(
        git.path, parent, shas["fix"], ["app.py"], ignore_whitespace=False, skip_useless=False
    )
    assert plain == {"app.py": [1, 6]}
    useful = deleted_lines(
        git.path, parent, shas["fix"], ["app.py"], ignore_whitespace=True, skip_useless=True
    )
    assert useful == {"app.py": [6]}
    assert blame_lines(git.path, parent, "app.py", [6], ignore_whitespace=True) == {shas["bug"]: 1}
    assert blame_lines(git.path, parent, "app.py", [1, 6], ignore_whitespace=False) == {
        shas["init"]: 1,
        shas["ws"]: 1,
    }


def test_review_sample(repo: tuple[GitRepo, dict[str, str]], tmp_path: Path) -> None:
    from aegis.mining.szz import review_sample

    git, shas = repo
    _szz(git, tmp_path / "out")
    sample = review_sample(tmp_path / "out", n=50)
    assert sample.height == 1
    row = sample.row(0, named=True)
    assert (row["fix_subject"], row["inducing_subject"]) == (
        "Fix off-by-one in total",
        "Count the header row",
    )
    assert row["correct"] == ""


def test_docstring_lines() -> None:
    from aegis.mining.szz import docstring_lines

    source = (
        '"""Modül."""\n'
        "class A:\n"
        '    """Sınıf\n'
        '    iki satır."""\n'
        "    def f(self):\n"
        '        """F."""\n'
        '        return "not a docstring"\n'
    )
    assert docstring_lines(source) == {1, 3, 4, 6}
    assert docstring_lines("print 'py2'\n") == set()


def test_ma_ignores_docstring_changes(tmp_path: Path) -> None:
    (tmp_path / "p").mkdir()
    git = GitRepo(tmp_path / "p")
    doc_v1 = 'def f(x):\n    """Return x."""\n    return x\n'
    git.commit("Add f", {"m.py": doc_v1}, date="2024-01-01T00:00:00+00:00")
    bug = git.commit("Tweak f", {"m.py": doc_v1.replace("return x\n", "return -x\n")})
    docs = git.commit(
        "Better wording",
        {"m.py": doc_v1.replace("return x\n", "return -x\n").replace("Return x.", "Gives x.")},
        date="2024-01-03T00:00:00+00:00",
    )
    fix = git.commit("Fix sign of f", {"m.py": doc_v1}, date="2024-01-04T00:00:00+00:00")
    ma = _szz(git, tmp_path / "ma", szz_variant="ma")
    assert ma.select("fix_sha", "inducing_sha").rows() == [(fix, bug)]
    b = _szz(git, tmp_path / "b", szz_variant="b")
    assert set(b["inducing_sha"]) == {bug, docs}


def test_full_history_is_default(tmp_path: Path) -> None:
    (tmp_path / "p").mkdir()
    git = GitRepo(tmp_path / "p")
    git.commit("Add module", {"m.py": "v = 1\n"}, date="2010-01-01T00:00:00+00:00")
    git.commit("Fix value", {"m.py": "v = 2\n"}, date="2011-01-01T00:00:00+00:00")
    git.commit("Update readme", {"README.md": "x\n"}, date="2026-01-01T00:00:00+00:00")
    cfg = MiningConfig()
    mine_repository(git.path, tmp_path / "o", cfg, functions=False)
    result = run_szz(git.path, tmp_path / "o", cfg)
    assert (result.fixes_in_window, result.inducing_commits) == (1, 1)
    windowed = MiningConfig(history_years=5)
    assert run_szz(git.path, tmp_path / "o", windowed).fixes_in_window == 0
