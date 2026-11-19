import json
from collections.abc import Collection, Mapping
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import pytest
from typer.testing import CliRunner

from aegis.cli import app
from aegis.mining import github_repository, is_remote, mine_repository, schema, slug_from_url
from tests.gitrepo import GitRepo

CALC_V1 = "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n"
CALC_V2 = "def add(a, b):\n    return a + b + 0\n\n\ndef sub(a, b):\n    return a - b\n"

History = tuple[GitRepo, dict[str, str]]


def _env(date: str) -> dict[str, str]:
    return {"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}


@pytest.fixture
def history(tmp_path: Path) -> History:
    """init → (feature dalı) → readme → merge → fix → docs; tarihler bilinen sırayla."""
    (tmp_path / "proj").mkdir()
    repo = GitRepo(tmp_path / "proj")
    shas = {
        "init": repo.commit(
            "Initial commit",
            {"calc.py": CALC_V1, "README.md": "# x\n", "old.txt": "x\n"},
            date="2024-01-01T10:00:00+03:00",
        )
    }
    repo.run("checkout", "-q", "-b", "feature")
    shas["feature"] = repo.commit(
        "Add mul",
        {"extra.py": "def mul(a, b):\n    return a * b\n"},
        date="2024-01-02T10:00:00+00:00",
    )
    repo.run("checkout", "-q", "main")
    shas["readme"] = repo.commit(
        "Tweak readme", {"README.md": "# y\n"}, date="2024-01-03T10:00:00+00:00"
    )
    repo.run(
        "merge", "-q", "--no-ff", "feature", "-m", "Merge branch 'feature', fix #3",
        env=_env("2024-01-04T10:00:00+00:00"),
    )  # fmt: skip
    shas["merge"] = repo.run("rev-parse", "HEAD")
    shas["fix"] = repo.commit(
        "Fix wrong result in add (closes #5)",
        {"calc.py": CALC_V2, "old.txt": None},
        date="2024-01-05T10:00:00+00:00",
        author=("Ayse", "ayse@example.com"),
    )
    shas["docs"] = repo.commit(
        "Fix typo in docs", {"README.md": "# z\n"}, date="2024-01-06T10:00:00+00:00"
    )
    return repo, shas


def _read(out: Path) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    return (
        pl.read_parquet(out / "commits.parquet"),
        pl.read_parquet(out / "files.parquet"),
        pl.read_parquet(out / "functions.parquet"),
    )


def test_mine_commits(history: History, tmp_path: Path) -> None:
    repo, shas = history
    result = mine_repository(repo.path, tmp_path / "out", slug="proj")
    commits, _, _ = _read(tmp_path / "out")

    assert commits.schema == pl.Schema(schema.COMMITS)
    assert result.commits == commits.height == 6
    assert (result.merges, result.fixes) == (1, 1)
    assert result.head_sha == shas["docs"]
    # PyDriller eskiden yeniye sıralar.
    assert commits["sha"].to_list()[0] == shas["init"]
    assert commits["sha"].to_list()[-1] == shas["docs"]

    by_sha = {row["sha"]: row for row in commits.iter_rows(named=True)}
    init = by_sha[shas["init"]]
    assert init["author_date"] == datetime(2024, 1, 1, 7, 0, tzinfo=UTC)
    assert init["author_utc_offset_minutes"] == 180
    assert init["parents"] == []

    merge = by_sha[shas["merge"]]
    assert merge["is_merge"] and len(merge["parents"]) == 2
    assert not merge["is_fix"] and "merge" in merge["fix_signals"]
    assert merge["files_changed"] == 0

    fix = by_sha[shas["fix"]]
    assert fix["is_fix"] and fix["linked_issues"] == [5]
    assert "closes:5" in fix["fix_signals"]
    assert fix["author_name"] == "Ayse"
    assert (fix["files_changed"], fix["lines_added"], fix["lines_deleted"]) == (2, 1, 2)

    docs = by_sha[shas["docs"]]
    assert not docs["is_fix"]
    assert "excluded:typo" in docs["fix_signals"]


def test_mine_files_and_functions(history: History, tmp_path: Path) -> None:
    repo, shas = history
    mine_repository(repo.path, tmp_path / "out", slug="proj")
    _, files, funcs = _read(tmp_path / "out")
    assert files.schema == pl.Schema(schema.FILES)
    assert funcs.schema == pl.Schema(schema.FUNCTIONS)

    fix_files = {
        (r["old_path"], r["new_path"], r["change_type"], r["is_python"])
        for r in files.filter(pl.col("sha") == shas["fix"]).iter_rows(named=True)
    }
    assert fix_files == {
        ("calc.py", "calc.py", "MODIFY", True),
        ("old.txt", None, "DELETE", False),
    }
    assert files.filter(pl.col("sha") == shas["merge"]).height == 0

    fix_funcs = funcs.filter(pl.col("sha") == shas["fix"])
    assert fix_funcs["name"].to_list() == ["add"]
    row = fix_funcs.row(0, named=True)
    assert (row["path"], row["start_line"], row["end_line"]) == ("calc.py", 1, 2)
    assert set(funcs.filter(pl.col("sha") == shas["init"])["name"]) == {"add", "sub"}


def test_mine_without_functions_and_since(history: History, tmp_path: Path) -> None:
    repo, shas = history
    since = datetime(2024, 1, 4, 12, tzinfo=UTC)
    result = mine_repository(repo.path, tmp_path / "out", functions=False, since=since)
    commits, _, funcs = _read(tmp_path / "out")
    assert commits["sha"].to_list() == [shas["fix"], shas["docs"]]
    assert funcs.height == 0 and result.functions == 0


def test_meta_and_label_source(history: History, tmp_path: Path) -> None:
    repo, shas = history
    asked: list[list[int]] = []

    def labels(numbers: Collection[int]) -> Mapping[int, Collection[str]]:
        asked.append(sorted(numbers))
        return {5: ["enhancement"]}

    result = mine_repository(repo.path, tmp_path / "out", slug="proj", label_source=labels)
    meta = json.loads((tmp_path / "out" / "meta.json").read_text("utf-8"))
    assert asked == [[5]]  # merge commit'indeki #3 sorulmaz
    assert meta["schema_version"] == schema.SCHEMA_VERSION
    assert meta["head_sha"] == shas["docs"]
    assert meta["issue_labels"] is True
    assert meta["mining_config"]["fix_patterns"]
    assert meta["commits"] == result.commits


def test_cli_mine(history: History, tmp_path: Path) -> None:
    repo, _ = history
    out = tmp_path / "data"
    result = CliRunner().invoke(app, ["mine", str(repo.path), "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert "6 commit (1 merge, 1 fix)" in result.output
    assert (out / "proj" / "commits.parquet").is_file()


def test_cli_mine_bad_repo(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["mine", str(tmp_path), "--out", str(tmp_path / "o")])
    assert result.exit_code == 2


@pytest.mark.parametrize(
    ("url", "slug", "gh"),
    [
        ("https://github.com/tqdm/tqdm", "tqdm__tqdm", "tqdm/tqdm"),
        ("https://github.com/httpie/cli.git", "httpie__cli", "httpie/cli"),
        ("git@github.com:psf/black.git", "psf__black", "psf/black"),
        ("https://gitlab.com/a/b/", "a__b", None),
    ],
)
def test_slugs(url: str, slug: str, gh: str | None) -> None:
    assert is_remote(url)
    assert slug_from_url(url) == slug
    assert github_repository(url) == gh


def test_local_path_is_not_remote() -> None:
    assert not is_remote("C:/Users/x/repo")
    assert not is_remote("../tqdm")


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[int] = []

    def get_issue_labels(self, number: int) -> list[str] | None:
        self.calls.append(number)
        return {1: ["bug"], 2: ["enhancement"]}.get(number)


def test_github_label_source_caches(tmp_path: Path) -> None:
    from aegis.mining.labels import github_label_source

    client = _FakeClient()
    cache = tmp_path / "labels.json"
    source = github_label_source(client, cache)  # type: ignore[arg-type]
    assert source([1, 2, 3]) == {1: ["bug"], 2: ["enhancement"], 3: []}
    assert source([1, 3, 4]) == {1: ["bug"], 3: [], 4: []}
    assert client.calls == [1, 2, 3, 4]  # cache'teki numaralar tekrar sorulmaz
    assert json.loads(cache.read_text("utf-8"))["1"] == ["bug"]


class _FakeIssueClient:
    def __init__(self) -> None:
        self.calls: list[int] = []

    def get_issue(self, number: int) -> dict[str, object] | None:
        self.calls.append(number)
        issues = {1: {"labels": ["bug"], "created_at": "2024-01-01T00:00:00Z", "pull": False}}
        return issues.get(number)


def test_github_issue_info_caches(tmp_path: Path) -> None:
    from aegis.mining.labels import github_issue_info

    client = _FakeIssueClient()
    cache = tmp_path / "issues.json"
    source = github_issue_info(client, cache)  # type: ignore[arg-type]
    first = source([1, 2])
    assert first[1] == {"labels": ["bug"], "created_at": "2024-01-01T00:00:00Z", "pull": False}
    assert first[2] is None  # bulunamayan numara
    assert source([1, 2, 3])[3] is None
    assert client.calls == [1, 2, 3]  # cache'teki numaralar (bulunamayanlar dahil) tekrar sorulmaz
    assert json.loads(cache.read_text("utf-8"))["2"] is None


def test_build_d1(tmp_path: Path) -> None:
    from aegis.mining.dataset import build_d1
    from aegis.mining.szz import run_szz

    (tmp_path / "p").mkdir()
    git = GitRepo(tmp_path / "p")
    git.commit("Add", {"a.py": "x = 1\ny = 2\n"}, date="2024-01-01T00:00:00+00:00")
    bug = git.commit("Change x", {"a.py": "x = 3\ny = 2\n"}, date="2024-02-01T00:00:00+00:00")
    git.commit("Docs", {"README.md": "r\n"}, date="2024-03-01T00:00:00+00:00")
    git.commit("Fix x", {"a.py": "x = 1\ny = 2\n"}, date="2024-04-01T00:00:00+00:00")
    root = tmp_path / "data"
    mine_repository(git.path, root / "p", slug="p", functions=False)
    commits = pl.read_parquet(root / "p" / "commits.parquet")
    files = pl.read_parquet(root / "p" / "files.parquet")
    from aegis.features import compute_kamei

    compute_kamei(commits, files).write_parquet(root / "p" / "kamei.parquet")
    run_szz(git.path, root / "p")

    stats = build_d1(root, root / "d1.parquet", min_positives=0)
    d1 = pl.read_parquet(root / "d1.parquet")
    assert [s.repo for s in stats] == ["p"]
    assert (stats[0].commits, stats[0].fixes, stats[0].positives) == (4, 1, 1)
    assert not stats[0].enough
    assert d1.filter("buggy")["sha"].to_list() == [bug]
    assert d1["as_of"].is_sorted()
    manifest = json.loads((root / "d1.json").read_text("utf-8"))
    assert manifest["rows"] == 4 and manifest["repos"][0]["head_sha"]
    assert manifest["repos"][0]["included"]

    # Varsayılan eşik (200): repo D1'e girmez ama manifestte kalır.
    build_d1(root, root / "d1.parquet")
    assert pl.read_parquet(root / "d1.parquet").height == 0
    manifest = json.loads((root / "d1.json").read_text("utf-8"))
    assert manifest["rows"] == 0 and not manifest["repos"][0]["included"]

    out = CliRunner().invoke(app, ["dataset", "--data", str(root), "--min-positives", "0"])
    assert out.exit_code == 0, out.output
    assert "Bug-inducing" in out.output


MINED = ("commits.parquet", "files.parquet", "functions.parquet", "kamei.parquet", "szz.parquet")


def _sorted(df: pl.DataFrame) -> pl.DataFrame:
    keys = [c for c, t in df.schema.items() if not isinstance(t, pl.List)]
    return df.sort(keys)


def _assert_same_output(a: Path, b: Path) -> None:
    for name in MINED:
        left, right = pl.read_parquet(a / name), pl.read_parquet(b / name)
        assert _sorted(left).equals(_sorted(right)), name


def _mine(repo: Path, out: Path, *extra: str) -> str:
    result = CliRunner().invoke(app, ["mine", str(repo), "--out", str(out), *extra])
    assert result.exit_code == 0, result.output
    return result.output


def _add_bug_and_fix(repo: GitRepo) -> str:
    bug = repo.commit(
        "Change sub",
        {"calc.py": CALC_V2.replace("a - b", "a - b - 1")},
        date="2024-01-07T10:00:00Z",
    )
    repo.commit("Fix sub off by one", {"calc.py": CALC_V2}, date="2024-01-08T10:00:00Z")
    return bug


def test_incremental_mining_matches_full_scan(history: History, tmp_path: Path) -> None:
    """Önceki çıktının üzerine yalnızca yeni commit'leri eklemek, sıfırdan taramayla aynı sonucu
    vermeli: commit, dosya, fonksiyon, Kamei ve SZZ çıktıları (#11)."""
    repo, _ = history
    inc, full = tmp_path / "inc", tmp_path / "full"
    _mine(repo.path, inc)
    bug = _add_bug_and_fix(repo)

    output = _mine(repo.path, inc)
    assert "yeni commit'leri tarıyor" in output and "2 yeni commit" in output
    meta = json.loads((inc / "proj" / "meta.json").read_text("utf-8"))
    assert meta["commits"] == 8 and meta["new_commits"] == 2
    assert meta["last_processed_sha"] == repo.run("rev-parse", "HEAD")
    assert bug in pl.read_parquet(inc / "proj" / "szz.parquet")["inducing_sha"].to_list()

    _mine(repo.path, full)
    _assert_same_output(inc / "proj", full / "proj")

    # Yeni commit yoksa hiçbir çıktı değişmez.
    before = {n: pl.read_parquet(inc / "proj" / n) for n in MINED}
    assert "0 yeni commit" in _mine(repo.path, inc)
    for name, frame in before.items():
        assert _sorted(pl.read_parquet(inc / "proj" / name)).equals(_sorted(frame)), name


def test_incremental_mining_falls_back_to_full_scan(history: History, tmp_path: Path) -> None:
    """Kayıtlı SHA artık geçmişte değilse (force push), ayarlar değiştiyse ya da --full verilirse
    tam tarama yapılır."""
    repo, shas = history
    out = tmp_path / "data"
    _mine(repo.path, out)
    repo.run("reset", "-q", "--hard", shas["fix"])  # docs commit'i geçmişten silindi
    _add_bug_and_fix(repo)
    output = _mine(repo.path, out)
    assert "yeni commit'leri tarıyor" not in output and "7 commit" in output
    _mine(repo.path, tmp_path / "ref")
    _assert_same_output(out / "proj", tmp_path / "ref" / "proj")

    assert "yeni commit" not in _mine(repo.path, out, "--full")
    assert "yeni commit" not in _mine(repo.path, out, "--no-functions")  # ayar değişti
