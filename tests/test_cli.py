import subprocess
from pathlib import Path

from typer.testing import CliRunner

from aegis import __version__
from aegis.cli import app

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def test_score_heuristic(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "README.md").write_text("x\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "base")
    _git(tmp_path, "checkout", "-q", "-b", "feature")
    (tmp_path / "auth").mkdir()
    (tmp_path / "auth" / "login.py").write_text("eval(token)\n", encoding="utf-8")
    (tmp_path / "uv.lock").write_text("lock\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "change")

    result = runner.invoke(app, ["score", "--base", "main", "--repo", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "(medium)" in result.output
    assert "riskli yol (auth, login)" in result.output
    assert "uv.lock (lock)" in result.output


def test_score_bad_ref(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    result = runner.invoke(app, ["score", "--base", "nope", "--repo", str(tmp_path)])
    assert result.exit_code == 2
