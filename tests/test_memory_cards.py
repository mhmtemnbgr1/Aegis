"""Hata kartı modeli ve oluşturucu (#22)."""

from pathlib import Path

from aegis.config import AegisConfig, MemoryConfig
from aegis.memory.cards import BugCard, build_cards, read_cards, write_cards
from aegis.mining import mine_repository
from aegis.mining.szz import run_szz
from tests.gitrepo import GitRepo

POOL_V1 = """\
class Pool:
    def release(self, conn):
        self.free.append(conn)

    def size(self):
        return len(self.free)
"""
POOL_BUG = POOL_V1.replace(
    "self.free.append(conn)", "if conn.ok:\n            self.free.append(conn)"
)
POOL_FIXED = POOL_BUG.replace("if conn.ok:", "if conn is not None:")


def _repo(tmp_path: Path) -> tuple[GitRepo, Path]:
    (tmp_path / "p").mkdir()
    git = GitRepo(tmp_path / "p")
    git.commit("Add pool", {"app/pool.py": POOL_V1}, date="2024-01-01T00:00:00+00:00")
    git.commit("Check conn", {"app/pool.py": POOL_BUG}, date="2024-02-01T00:00:00+00:00")
    git.commit(
        "Fix release of broken connections (#89)\n\nCloses #89",
        {"app/pool.py": POOL_FIXED, "tests/test_pool.py": "def test_x():\n    pass\n"},
        date="2024-03-01T00:00:00+00:00",
    )
    git.commit("Fix typo in docs", {"README.md": "x\n"}, date="2024-04-01T00:00:00+00:00")
    data = tmp_path / "data"
    mine_repository(git.path, data, functions=False)
    run_szz(git.path, data)
    return git, data


def test_model_fields_match_architecture_doc() -> None:
    assert list(BugCard.model_fields) == [
        "id", "fix_sha", "fix_date", "inducing_shas", "issue", "files", "functions",
        "message", "before", "after", "fix_diff", "summary",
    ]  # fmt: skip


def test_build_cards(tmp_path: Path) -> None:
    git, data = _repo(tmp_path)
    titles = {89: "Memory leak in connection pool"}
    cards = list(
        build_cards(git.path, data, issue_titles=lambda ns: {n: titles.get(n) for n in ns})
    )
    assert len(cards) == 1  # doküman fix'i kaynak dosyaya dokunmuyor
    card = cards[0]
    bug = git.run("rev-list", "--max-count=1", "--skip=2", "HEAD")
    assert card.id == f"BC-{card.fix_sha[:10]}"
    assert card.inducing_shas == [bug]
    assert card.issue is not None and card.issue.number == 89
    assert card.issue.title == "Memory leak in connection pool"
    assert card.files == ["app/pool.py"]  # test dosyası hariç
    assert card.functions == ["app.pool.Pool.release"]
    assert "if conn.ok:" in card.before and "if conn is not None:" in card.after
    assert "def size" not in card.before
    assert "-        if conn.ok:" in card.fix_diff
    assert card.summary == "Fix release of broken connections (#89)"


def test_cards_roundtrip_and_skip(tmp_path: Path) -> None:
    git, data = _repo(tmp_path)
    cfg = AegisConfig(memory=MemoryConfig(max_diff_lines=3))
    cards = list(build_cards(git.path, data, cfg))
    assert cards[0].fix_diff.splitlines()[-1].startswith("... (")
    assert cards[0].issue is not None and cards[0].issue.title is None  # issue kaynağı yok
    path = tmp_path / "cards.jsonl"
    assert write_cards(path, cards) == 1
    assert read_cards(path) == cards
    assert list(build_cards(git.path, data, cfg, skip={cards[0].fix_sha})) == []


def test_cli_index_is_incremental(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from aegis.cli import app

    git, data = _repo(tmp_path)
    root = tmp_path / "root"
    root.mkdir()
    (data).rename(root / "p")  # slug = repo dizin adı (remote yok)
    runner = CliRunner()
    idx = ["--index", str(tmp_path / "idx")]
    first = runner.invoke(app, ["index", str(git.path), "--data", str(root), *idx])
    assert first.exit_code == 0, first.output
    assert "1 yeni kart" in first.output
    second = runner.invoke(app, ["index", str(git.path), "--data", str(root), *idx])
    assert "0 yeni kart · toplam 1" in second.output
    rebuilt = runner.invoke(app, ["index", str(git.path), "--data", str(root), "--rebuild", *idx])
    assert "1 yeni kart · toplam 1" in rebuilt.output
    assert len(read_cards(root / "p" / "cards.jsonl")) == 1
    assert (tmp_path / "idx" / "p" / "index.json").is_file()
    assert "İndeks: 1 kart · lsa" in rebuilt.output
    missing = runner.invoke(app, ["index", str(git.path), "--data", str(tmp_path / "yok")])
    assert missing.exit_code == 2


def test_issue_title_source_caches(tmp_path: Path) -> None:
    from aegis.mining.labels import github_issue_titles

    calls: list[int] = []

    class Client:
        def get_issue_title(self, number: int) -> str | None:
            calls.append(number)
            return None if number == 2 else f"Issue {number}"

    cache = tmp_path / "titles.json"
    source = github_issue_titles(Client(), cache)  # type: ignore[arg-type]
    assert source([1, 2]) == {1: "Issue 1", 2: None}
    assert source([1, 2, 3]) == {1: "Issue 1", 2: None, 3: "Issue 3"}
    assert calls == [1, 2, 3]
