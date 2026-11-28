"""Gatekeeper seçimi, model gatekeeper'ı ve çalışma anı bütçe eşiği (#66)."""

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from aegis.config import AegisConfig, GatekeeperConfig
from aegis.diff import git_diff, parse_diff
from aegis.gatekeeper import HeuristicGatekeeper
from aegis.gatekeeper.factory import ModelGatekeeper, make_gatekeeper, recent_scores
from aegis.gatekeeper.model import TrainedModel
from aegis.gatekeeper.score import budget_bands
from aegis.review import ReviewStatus, run_review
from aegis.telemetry.runs import run_record
from tests.gitrepo import GitRepo
from tests.test_score import _model, project  # noqa: F401  (fixture)

NOW = datetime(2024, 5, 1, tzinfo=UTC)


def _config(tmp_path: Path, data: Path, **gk: object) -> AegisConfig:
    return AegisConfig.model_validate(
        {
            "gatekeeper": {"mode": "model", "models_dir": str(tmp_path / "models"), **gk},
            "mining": {"data_dir": str(data)},
            "review": {"runs_path": str(tmp_path / "runs.jsonl")},
        }
    )


def test_heuristic_is_default(tmp_path: Path) -> None:
    gk, warning = make_gatekeeper(AegisConfig(), tmp_path, "main", "HEAD")
    assert isinstance(gk, HeuristicGatekeeper) and warning is None


def test_model_mode_uses_model(project: tuple[GitRepo, Path], tmp_path: Path) -> None:  # noqa: F811
    git, data = project
    _model(tmp_path)
    config = _config(tmp_path, data)
    gk, warning = make_gatekeeper(config, git.path, "main", "feature")
    assert isinstance(gk, ModelGatekeeper) and warning is None
    diff = parse_diff(git_diff("main", "feature", repo=git.path))
    risk = gk.assess(diff, as_of=NOW)
    assert risk.source == "model"
    assert risk.features["commits"] == 2
    assert any("riski artırıyor" in r for r in risk.reasons)
    assert risk.reasons[-1] == "model: proj/lr-none"

    result = run_review(
        git_diff("main", "feature", repo=git.path), config, llm_enabled=False, gatekeeper=gk
    )
    assert result.risk is not None and result.risk.source == "model"
    assert result.status in {ReviewStatus.SKIPPED_LOW_RISK, ReviewStatus.SKIPPED_NO_LLM}
    assert run_record(result)["gatekeeper"] == "model"


def test_model_mode_falls_back(project: tuple[GitRepo, Path], tmp_path: Path) -> None:  # noqa: F811
    git, data = project
    config = _config(tmp_path, data)
    gk, warning = make_gatekeeper(config, git.path, "main", "feature")
    assert isinstance(gk, HeuristicGatekeeper) and "Model bulunamadı" in (warning or "")

    _model(tmp_path)
    no_data = _config(tmp_path, tmp_path / "bos")
    gk, warning = make_gatekeeper(no_data, git.path, "main", "feature")
    assert isinstance(gk, HeuristicGatekeeper) and "madencilik geçmişi yok" in (warning or "")

    # Puanlama sırasında hata (ör. geçersiz ref): sezgisel kurala döner, inceleme sürer.
    broken, _ = make_gatekeeper(config, git.path, "yok", "feature")
    risk = broken.assess(parse_diff(git_diff("main", "feature", repo=git.path)), as_of=NOW)
    assert risk.source == "heuristic"
    assert "model kullanılamadı" in risk.reasons[-1]


def test_recent_scores(tmp_path: Path) -> None:
    runs = tmp_path / "runs.jsonl"
    assert recent_scores(runs, 10) == []
    lines = [
        {"gatekeeper": "model", "risk_score": 0.1},
        {"gatekeeper": "heuristic", "risk_score": 0.9},
        {"gatekeeper": "model", "risk_score": None},
        {"risk_score": 0.5},
        {"gatekeeper": "model", "risk_score": 0.3},
    ]
    runs.write_text("\n".join(json.dumps(x) for x in lines) + "\nbozuk satır\n", encoding="utf-8")
    assert recent_scores(runs, 10) == [0.1, 0.3]
    assert recent_scores(runs, 1) == [0.3]


def test_budget_bands_prefer_recent_scores(tmp_path: Path) -> None:
    model = TrainedModel.load(_model(tmp_path))
    fixed = AegisConfig()
    assert budget_bands(model, fixed)[2] == "config"

    budget = AegisConfig(gatekeeper=GatekeeperConfig(max_llm_pr_ratio=0.2, budget_min_runs=20))
    low, _, source = budget_bands(model, budget, [0.5] * 5)
    assert source == "doğrulama"
    assert np.mean(np.asarray(model.valid_scores) >= low) <= 0.2

    recent = [i / 100 for i in range(100)]
    low, high, source = budget_bands(model, budget, recent)
    assert source == "son 50 PR"  # budget_window varsayılanı
    window = np.asarray(recent[-50:])
    assert np.mean(window >= low) <= 0.2 and low <= high


def test_safety_threshold_policy_uses_validation_labels(tmp_path: Path) -> None:
    model = TrainedModel.load(_model(tmp_path))
    model.valid_scores = [0.9, 0.8, 0.7, 0.6]
    model.valid_labels = [1, 0, 1, 0]
    config = AegisConfig(
        gatekeeper=GatekeeperConfig(threshold_policy="safety", safety_recall_target=0.5)
    )

    low, high, source = budget_bands(model, config)
    assert low == 0.9
    assert high == max(low, config.gatekeeper.high_threshold)
    assert source == "doğrulama (recall ≥ %50)"


def test_safety_threshold_policy_falls_back_without_validation_labels(tmp_path: Path) -> None:
    model = TrainedModel.load(_model(tmp_path))
    model.valid_labels = []
    config = AegisConfig(gatekeeper=GatekeeperConfig(threshold_policy="safety"))

    assert budget_bands(model, config) == (
        config.gatekeeper.low_threshold,
        config.gatekeeper.high_threshold,
        "config (doğrulama etiketi yok)",
    )
