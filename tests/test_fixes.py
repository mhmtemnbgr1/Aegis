import pytest

from aegis.config import MiningConfig, parse_config
from aegis.mining import FixClassifier, linked_issues

clf = FixClassifier()


@pytest.mark.parametrize(
    "message",
    [
        "Fix crash when total is None",
        "fixes #123: wrong rounding",
        "Fixed off-by-one in rate calculation",
        "bugfix: handle empty iterables",
        "Avoid memory leak in monitor thread",
        "Prevent regression in nested bars (#55)",
        "Handle KeyError\n\nThis crashed on Windows.",
    ],
)
def test_fix_keywords(message: str) -> None:
    result = clf.classify(message)
    assert result.is_fix, result
    assert any(s.startswith("keyword:") for s in result.signals)


@pytest.mark.parametrize(
    "message",
    [
        "Add dark mode",
        "Refactor progress rendering",
        "Bump version to 4.66",
        "Prefix the output with a timestamp",  # 'fix' kelime içinde
        "Debugging helpers",  # 'bug' kelime içinde
    ],
)
def test_not_fix(message: str) -> None:
    assert not clf.classify(message).is_fix


@pytest.mark.parametrize(
    "message",
    [
        "Fix typo in README",
        "fix docs build",
        "Fix flake8 warnings",
        'Revert "Fix crash in close()"',
        "CI: fix windows job",
    ],
)
def test_excluded(message: str) -> None:
    result = clf.classify(message)
    assert not result.is_fix
    assert any(s.startswith("excluded:") for s in result.signals)


def test_exclusion_only_on_subject() -> None:
    assert clf.classify("Fix crash on empty input\n\nAlso update the docs.").is_fix


def test_bug_label_makes_fix() -> None:
    result = clf.classify("Handle empty input (closes #12)", issue_labels={12: ["Bug"]})
    assert result.is_fix
    assert "label:bug#12" in result.signals
    assert "closes:12" in result.signals


def test_closing_ref_alone_is_not_fix() -> None:
    result = clf.classify("Add --color option, closes #7", issue_labels={7: ["enhancement"]})
    assert not result.is_fix
    assert result.linked_issues == (7,)


def test_label_overrides_exclusion() -> None:
    result = clf.classify("Fix typo that broke parsing #9", issue_labels={9: ["type: bug"]})
    assert result.is_fix


def test_merge_never_fix() -> None:
    result = clf.classify("Merge pull request #40 from x/fix-crash", is_merge=True)
    assert not result.is_fix
    assert "merge" in result.signals
    assert result.linked_issues == (40,)


def test_linked_issues() -> None:
    message = "Fix #12 and GH-15; see #12, other/repo#99, http://x/y#3 and abc#4 (#20)"
    assert linked_issues(message) == (12, 15, 20)


def test_custom_patterns_from_toml() -> None:
    toml = (
        "[mining]\n"
        "fix_patterns = ['\\bhata\\b']\n"
        "fix_exclude_patterns = []\n"
        "bug_labels = ['kusur']\n"
    )
    config = parse_config(toml).mining
    custom = FixClassifier(config)
    assert custom.classify("Ayrıştırmadaki hata giderildi").is_fix
    assert not custom.classify("Fix crash").is_fix
    assert custom.classify("Refactor #3", issue_labels={3: ["Kusur"]}).is_fix


def test_invalid_regex_rejected() -> None:
    with pytest.raises(ValueError, match="geçersiz regex"):
        MiningConfig(fix_patterns=["("])


@pytest.mark.parametrize(
    "message",
    [
        "fix tests",
        "test: Fix ResolveTimeoutTestCase",
        "fix smoothing test",
        "Fix broken link",
        "iostream: Fix copy/pasted comment",
        "Fix style, add comments",
        "Fix appveyor.yml",
        "fix: action version",
        ":lock: Fix development dependencies security (#174)",
        "✅ Fix frontend test timeout with Starlette Git (#16408)",
        "👷 Fix checkout GitHub Action fetch-depth",
    ],
)
def test_non_bug_fixes_are_excluded(message: str) -> None:
    assert not FixClassifier().classify(message).is_fix


def test_subject_only_mode() -> None:
    message = "Add option to disable progress bar.\n\nShould fix GH-1"
    assert FixClassifier().classify(message).is_fix
    subject_only = MiningConfig(fix_subject_only=True)
    assert not FixClassifier(subject_only).classify(message).is_fix
    assert FixClassifier(subject_only).classify("Fix crash on empty input").is_fix


def test_reclassify_updates_mined_output(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from aegis.mining import mine_repository
    from aegis.mining.miner import reclassify
    from tests.gitrepo import GitRepo

    (tmp_path / "r").mkdir()
    git = GitRepo(tmp_path / "r")
    git.commit("Add core", {"core.py": "a = 1\n"})
    git.commit("fix tests", {"core.py": "a = 2\n"}, date="2024-02-01T00:00:00+00:00")
    git.commit("Fix crash", {"core.py": "a = 3\n"}, date="2024-03-01T00:00:00+00:00")
    old = MiningConfig(fix_exclude_patterns=[])
    mine_repository(git.path, tmp_path / "o", old, functions=False)
    import polars as pl

    from aegis.features.kamei import compute_kamei

    commits = pl.read_parquet(tmp_path / "o" / "commits.parquet")
    compute_kamei(commits, pl.read_parquet(tmp_path / "o" / "files.parquet")).write_parquet(
        tmp_path / "o" / "kamei.parquet"
    )
    assert reclassify(tmp_path / "o", MiningConfig()) == (2, 1)
    kamei = pl.read_parquet(tmp_path / "o" / "kamei.parquet").sort("as_of")
    assert kamei["fix"].to_list() == [0.0, 0.0, 1.0]
