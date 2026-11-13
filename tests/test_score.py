"""`aegis score` ile model tabanlı puanlama (#20)."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from aegis.cli import app
from aegis.config import AegisConfig, TrainingConfig
from aegis.features.history import FileChange
from aegis.gatekeeper.model import train_model
from aegis.gatekeeper.score import (
    find_model,
    load_history,
    parse_file_changes,
    range_commits,
    range_features,
)
from aegis.gatekeeper.split import time_split
from aegis.mining import mine_repository
from tests.gitrepo import GitRepo
from tests.test_gk_model import _d1

runner = CliRunner()
NUL = chr(0)


def test_parse_file_changes() -> None:
    name_status = NUL.join(
        ["\nM", "a.py", "A", "new.py", "D", "old.py", "R087", "src/x.py", "src/y.py", ""]
    )
    numstat = NUL.join(
        ["\n3\t1\ta.py", "5\t0\tnew.py", "0\t9\told.py", "2\t2\t", "src/x.py", "src/y.py", ""]
    )
    assert parse_file_changes(name_status, numstat) == (
        FileChange("a.py", "a.py", 3, 1),
        FileChange(None, "new.py", 5, 0),
        FileChange("old.py", None, 0, 9),
        FileChange("src/x.py", "src/y.py", 2, 2),
    )
    binary = parse_file_changes(NUL.join(["M", "img.png", ""]), NUL.join(["-\t-\timg.png", ""]))
    assert binary == (FileChange("img.png", "img.png", 0, 0),)


@pytest.fixture
def project(tmp_path: Path) -> tuple[GitRepo, Path]:
    """Madenciliği yapılmış `main` ve üzerinde iki commit'lik bir `feature` dalı."""
    (tmp_path / "proj").mkdir()
    git = GitRepo(tmp_path / "proj")
    git.commit("Add core", {"pkg/core.py": "a = 1\nb = 2\n"}, date="2024-01-01T00:00:00+00:00")
    git.commit("Fix core bug", {"pkg/core.py": "a = 1\nb = 3\n"}, date="2024-02-01T00:00:00+00:00")
    git.commit(
        "Add util",
        {"pkg/util.py": "x = 1\n"},
        date="2024-03-01T00:00:00+00:00",
        author=("Other", "other@example.com"),
    )
    data = tmp_path / "data"
    mine_repository(git.path, data / "proj", functions=False)
    git.run("checkout", "-q", "-b", "feature")
    git.commit(
        "Extend core",
        {"pkg/core.py": "a = 1\nb = 3\nc = 4\nd = 5\n", "pkg/new.py": "n = 1\n"},
        date="2024-04-01T00:00:00+00:00",
    )
    git.commit("Fix util crash", {"pkg/util.py": "x = 2\n"}, date="2024-04-02T00:00:00+00:00")
    return git, data


def test_range_features_use_history(project: tuple[GitRepo, Path]) -> None:
    git, data = project
    commits = range_commits(git.path, "main", "feature", AegisConfig())
    assert [c.subject for c in commits] == ["Extend core", "Fix util crash"]
    assert [c.is_fix for c in commits] == [False, True]
    rows = range_features(commits, load_history(data / "proj")).to_dicts()
    first, second = rows
    # core.py'a 2 satır, yeni new.py'a 1 satır; lt yalnızca core.py'ın önceki 2 satırı.
    assert (first["la"], first["ld"], first["nf"], first["lt"]) == (3, 0, 2, 2)
    assert first["nuc"] == 2  # core.py iki commit'te değişmiş; new.py yeni
    assert first["exp"] == 2  # Dev'in main'deki iki commit'i
    assert second["exp"] == 3  # aralığın ilk commit'i de geçmişe eklendi
    assert second["fix"] == 1
    assert second["ndev"] == 1  # util.py'a yalnızca Other dokunmuş


def _model(tmp_path: Path) -> Path:
    split = time_split(_d1(400, seed=5), TrainingConfig(label_delay_days=14))
    path = tmp_path / "models" / "proj" / "lr-none.pkl"
    train_model(split, "lr", seed=0).save(path)
    return path


def test_cli_score_with_model(project: tuple[GitRepo, Path], tmp_path: Path) -> None:
    git, data = project
    model = _model(tmp_path)
    assert find_model(tmp_path / "models", "proj") == model
    args = ["score", "main..feature", "--repo", str(git.path), "--data", str(data)]
    result = runner.invoke(app, [*args, "--model", str(model)])
    assert result.exit_code == 0, result.output
    assert "Risk:" in result.output and "Model:" in result.output
    assert "2 commit" in result.output
    assert "Extend core" in result.output and "Fix util crash" in result.output
    assert "(riski artırıyor)" in result.output


def test_cli_score_falls_back_to_heuristic(project: tuple[GitRepo, Path], tmp_path: Path) -> None:
    git, _ = project
    args = ["score", "main..feature", "--repo", str(git.path)]
    missing = runner.invoke(app, [*args, "--model", str(tmp_path / "yok.pkl")])
    assert missing.exit_code == 0, missing.output
    assert "Model bulunamadı" in missing.output and "satır değişti" in missing.output
    no_data = runner.invoke(
        app, [*args, "--model", str(_model(tmp_path)), "--data", str(tmp_path / "bos")]
    )
    assert no_data.exit_code == 0, no_data.output
    assert "madencilik geçmişi yok" in no_data.output
    bad = runner.invoke(app, ["score", "main...feature", "--repo", str(git.path)])
    assert bad.exit_code == 2
