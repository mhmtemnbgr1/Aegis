"""Aegis'e özgü diff özellikleri: riskli yol ve test oranı (FR-12)."""

from aegis.config import AegisConfig
from aegis.features import extra
from aegis.features.history import Change, FileChange

CFG = AegisConfig()
RISKY = CFG.gatekeeper.heuristic.risky_paths
TESTS = CFG.mining.test_path_patterns


def _change(*files: FileChange) -> Change:
    return Change("dev", files)


def test_risky_files_counts_path_words() -> None:
    change = _change(
        FileChange("app/auth/login.py", "app/auth/login.py", 3, 1),
        FileChange(None, "app/db_pool.py", 2, 0),
        FileChange("docs/author.md", "docs/author.md", 1, 1),  # "author" ≠ "auth"
    )
    assert extra.risky_files(change, RISKY) == 2


def test_test_change_ratio() -> None:
    change = _change(
        FileChange("pkg/core.py", "pkg/core.py", 6, 2),
        FileChange(None, "tests/test_core.py", 2, 0),
    )
    assert extra.test_ratio(change, TESTS) == 0.2
    assert extra.test_ratio(_change(), TESTS) == 0.0
    assert extra.extra_metrics(change, risky=RISKY, test_patterns=TESTS) == {
        "risky_files": 0.0,
        "test_ratio": 0.2,
    }
