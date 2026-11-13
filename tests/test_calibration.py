"""Kalibrasyon, bütçe eşiği ve PR skoru (#18)."""

import numpy as np
import pytest

from aegis.config import GatekeeperConfig, TrainingConfig
from aegis.gatekeeper.calibration import (
    budget_thresholds,
    ece,
    fit_calibrator,
    pr_score,
    reliability,
)
from aegis.gatekeeper.model import train_model
from aegis.gatekeeper.split import time_split
from tests.test_gk_model import _d1


def _overconfident(n: int = 4000, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Gerçek olasılık q; model skoru q'yu abartıyor (q=0.2 → skor ~0.6)."""
    rng = np.random.default_rng(seed)
    q = rng.uniform(0.0, 0.4, n)
    y = rng.random(n) < q
    return np.clip(q * 3, 0, 1), y


@pytest.mark.parametrize("method", ["sigmoid", "isotonic"])
def test_calibration_reduces_error(method: str) -> None:
    score, y = _overconfident()
    cal = fit_calibrator(method, score[:2000], y[:2000])  # type: ignore[arg-type]
    after = cal.apply(score[2000:])
    assert ece(y[2000:], after) < ece(y[2000:], score[2000:]) / 2
    # Sıralama korunur (isotonic eşitlik üretebilir).
    order = np.argsort(score[2000:])
    assert np.all(np.diff(after[order]) >= -1e-9)


def test_calibration_single_class_is_identity() -> None:
    cal = fit_calibrator("sigmoid", [0.1, 0.9], [0, 0])
    assert cal.method == "none"
    assert np.allclose(cal.apply([0.1, 0.9]), [0.1, 0.9])


def test_reliability_bins() -> None:
    rows = reliability([0, 1, 1, 0], [0.05, 0.95, 0.91, 0.08])
    assert rows == [[0.065, 0.0, 2.0], [0.9299999999999999, 1.0, 2.0]]
    assert ece([0, 1], [0.0, 1.0]) == 0.0


def test_budget_thresholds_respect_budget() -> None:
    scores = np.linspace(0, 1, 101)
    low, high = budget_thresholds(scores, 0.2)
    assert np.mean(scores >= low) <= 0.2
    assert np.mean(scores >= low) > 0.19
    assert np.mean(scores >= high) <= 0.1
    assert low <= high


def test_budget_thresholds_with_ties() -> None:
    scores = [0.1] * 50 + [0.5] * 40 + [0.9] * 10
    low, high = budget_thresholds(scores, 0.3)
    # 0.5 seçilirse %50 gider; bütçe %30 olduğu için yalnızca 0.9 ve üstü.
    assert (low, high) == (0.9, 0.9)
    nothing, _ = budget_thresholds([0.5] * 10, 0.3)
    assert nothing > 0.5
    with pytest.raises(ValueError):
        budget_thresholds(scores, 0.0)


def test_pr_score() -> None:
    assert pr_score([]) == 0.0
    assert pr_score([0.5]) == 0.5
    assert pr_score([0.5, 0.5]) == pytest.approx(0.75)
    assert pr_score([0.1, 0.2, 0.3]) > max(0.1, 0.2, 0.3)


def test_model_is_calibrated_and_budgeted() -> None:
    split = time_split(_d1(800, seed=3), TrainingConfig(label_delay_days=14))
    model = train_model(split, "rf", calibration="sigmoid", seed=0)
    assert model.calibrator.method == "sigmoid"
    raw = train_model(split, "rf", calibration="none", seed=0)
    # Platt, doğrulama kümesinde log-loss'u en aza indirir; orada ham skordan kötü olamaz.
    # (ECE'ye etkisi veriye bağlıdır; gerçek veride ölçüldü, bkz. docs/architecture.md #18.)
    from sklearn.metrics import log_loss

    y_valid = split.valid["buggy"].to_numpy()
    calibrated = log_loss(y_valid, model.predict_proba(split.valid))
    assert calibrated <= log_loss(y_valid, raw.predict_proba(split.valid)) + 1e-9
    assert model.test["roc_auc"] == pytest.approx(raw.test["roc_auc"], abs=1e-9)
    low, high = model.thresholds(0.2)
    assert np.mean(np.asarray(model.valid_scores) >= low) <= 0.2
    assert low <= high
    assert set(model.budget) == {"0.1", "0.2", "0.3", "0.5"}
    assert model.reliability
    commits = split.test.head(3)
    assert model.score_pr(commits) >= model.predict_proba(commits).max()


def test_config_budget_fields() -> None:
    cfg = GatekeeperConfig(max_llm_pr_ratio=0.3)
    assert cfg.high_share == 0.5
    with pytest.raises(ValueError):
        GatekeeperConfig(max_llm_pr_ratio=0.0)
