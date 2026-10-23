import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from aegis.config import AegisConfig, GatekeeperConfig, HeuristicConfig, load_config
from aegis.diff import Diff, DiffLine, FileDiff, FileStatus, Hunk, LineKind
from aegis.gatekeeper import Gatekeeper, HeuristicGatekeeper, RiskBand, band_for
from aegis.gatekeeper.heuristic import is_test_file

NOW = datetime(2026, 10, 23, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[1]


def _file(path: str, added: list[str], removed: int = 0) -> FileDiff:
    lines = [DiffLine(kind=LineKind.REMOVED, content="old", old_lineno=1) for _ in range(removed)]
    lines += [
        DiffLine(kind=LineKind.ADDED, content=text, new_lineno=i)
        for i, text in enumerate(added, start=1)
    ]
    hunk = Hunk(old_start=1, old_length=removed, new_start=1, new_length=len(added), lines=lines)
    return FileDiff(path=path, status=FileStatus.MODIFIED, hunks=[hunk])


def _assess(*files: FileDiff, config: GatekeeperConfig | None = None) -> tuple[float, RiskBand]:
    result = HeuristicGatekeeper(config).assess(Diff(files=list(files)), as_of=NOW)
    return result.score, result.band


def test_implements_protocol() -> None:
    gatekeeper: Gatekeeper = HeuristicGatekeeper()
    assert gatekeeper.assess(Diff(), as_of=NOW).band is RiskBand.LOW


@pytest.mark.parametrize(
    ("score", "band"),
    [(0.0, RiskBand.LOW), (0.29, RiskBand.LOW), (0.3, RiskBand.MEDIUM), (0.7, RiskBand.HIGH)],
)
def test_band_for(score: float, band: RiskBand) -> None:
    assert band_for(score, 0.3, 0.7) is band


def test_small_harmless_change_is_low() -> None:
    score, band = _assess(_file("app/utils.py", ["x = 1"] * 5))
    assert band is RiskBand.LOW
    assert score == pytest.approx(0.4 * 5 / 400)


def test_large_change_is_medium() -> None:
    _, band = _assess(_file("app/utils.py", ["x = 1"] * 400))
    assert band is RiskBand.MEDIUM


def test_risky_path_and_api_is_high() -> None:
    result = HeuristicGatekeeper().assess(
        Diff(
            files=[
                _file(
                    "app/db/queries.py",
                    ['cur.execute("SELECT * FROM t WHERE id=" + uid)', "x = 1"] * 50,
                )
            ]
        ),
        as_of=NOW,
    )
    assert result.band is RiskBand.HIGH
    assert result.features["risky_api_calls"] == 50
    assert result.features["risky_path_files"] == 1
    assert any("riskli yol (db)" in r for r in result.reasons)
    assert any("riskli API" in r for r in result.reasons)


@pytest.mark.parametrize(
    "line",
    [
        "eval(user_input)",
        "subprocess.run(cmd, shell=True)",
        "os.system(cmd)",
        "data = pickle.loads(blob)",
        "yaml.load(fh)",
        "requests.get(url, verify=False)",
        'cursor.execute(f"SELECT * FROM users WHERE name = {name}")',
        'cursor.execute("DELETE FROM t WHERE id = %s" % uid)',
    ],
)
def test_risky_api_patterns(line: str) -> None:
    result = HeuristicGatekeeper().assess(Diff(files=[_file("app/x.py", [line])]), as_of=NOW)
    assert result.features["risky_api_calls"] == 1


@pytest.mark.parametrize(
    "line",
    [
        'cursor.execute("SELECT * FROM t WHERE id = %s", (uid,))',
        "evaluate(model)",
        "self.retrieval(x)",
    ],
)
def test_safe_lines_not_flagged(line: str) -> None:
    result = HeuristicGatekeeper().assess(Diff(files=[_file("app/x.py", [line])]), as_of=NOW)
    assert result.features["risky_api_calls"] == 0


def test_path_matches_whole_words_only() -> None:
    result = HeuristicGatekeeper().assess(
        Diff(files=[_file("app/dashboard/author.py", ["x"])]), as_of=NOW
    )
    assert result.features["risky_path_files"] == 0


def test_test_files_ignored_for_api() -> None:
    result = HeuristicGatekeeper().assess(
        Diff(files=[_file("tests/test_x.py", ["eval('1')"])]), as_of=NOW
    )
    assert result.features["risky_api_calls"] == 0


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("tests/test_a.py", True),
        ("pkg/test/helpers.py", True),
        ("pkg/a_test.py", True),
        ("conftest.py", True),
        ("app/testing.py", False),
        ("app/contest.py", False),
    ],
)
def test_is_test_file(path: str, expected: bool) -> None:
    assert is_test_file(path) is expected


def test_weights_from_config() -> None:
    path_only = GatekeeperConfig(
        heuristic=HeuristicConfig(size_weight=0, path_weight=1, api_weight=0)
    )
    score, band = _assess(_file("app/auth/login.py", ["x = 1"]), config=path_only)
    assert (score, band) == (1.0, RiskBand.HIGH)

    custom_thresholds = GatekeeperConfig(low_threshold=0.0, high_threshold=0.001)
    _, band = _assess(_file("app/utils.py", ["x = 1"] * 5), config=custom_thresholds)
    assert band is RiskBand.HIGH


def test_invalid_config() -> None:
    with pytest.raises(ValidationError):
        GatekeeperConfig(low_threshold=0.8, high_threshold=0.2)
    with pytest.raises(ValidationError):
        HeuristicConfig(size_weight=0, path_weight=0, api_weight=0)


def test_load_config_defaults_and_toml(tmp_path: Path) -> None:
    assert load_config(tmp_path) == AegisConfig()
    (tmp_path / ".aegis.toml").write_text(
        "[gatekeeper]\nlow_threshold = 0.1\n[gatekeeper.heuristic]\nrisky_paths = ['billing']\n"
        "[agents.analyst]\nprovider = 'ollama'\n",
        encoding="utf-8",
    )
    config = load_config(tmp_path)
    assert config.gatekeeper.low_threshold == 0.1
    assert config.gatekeeper.heuristic.risky_paths == ["billing"]


def test_example_config_is_valid(tmp_path: Path) -> None:
    shutil.copy(ROOT / ".aegis.toml.example", tmp_path / ".aegis.toml")
    assert load_config(tmp_path).gatekeeper == GatekeeperConfig()
