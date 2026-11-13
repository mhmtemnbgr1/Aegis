"""Risk modelleri ve `aegis train` (#15)."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import pytest
from typer.testing import CliRunner

from aegis.cli import app
from aegis.config import TrainingConfig
from aegis.features.kamei import KAMEI
from aegis.gatekeeper.model import MODELS, TrainedModel, train_model
from aegis.gatekeeper.split import time_split

START = datetime(2022, 1, 1, tzinfo=UTC)


def _d1(n: int = 400, seed: int = 0) -> pl.DataFrame:
    """Büyük ve dağınık commit'lerin daha sık hatalı olduğu sentetik D1."""
    rng = np.random.default_rng(seed)
    data: dict[str, object] = {name: rng.integers(0, 20, n).astype(float) for name in KAMEI}
    la = rng.exponential(30, n)
    nf = rng.integers(1, 8, n).astype(float)
    data["la"], data["nf"] = la, nf
    risk = 1 / (1 + np.exp(-(0.04 * la + 0.4 * nf - 4)))
    buggy = rng.random(n) < risk
    when = [START + timedelta(days=i) for i in range(n)]
    return pl.DataFrame(
        {
            "repo": ["r"] * n,
            "sha": [f"c{i}" for i in range(n)],
            "as_of": when,
            **data,
            "fixed_at": [
                w + timedelta(days=7) if b else None for w, b in zip(when, buggy, strict=True)
            ],
        },
        schema_overrides={"fixed_at": pl.Datetime("us", "UTC")},
    ).with_columns(pl.col("fixed_at").is_not_null().alias("buggy"))


@pytest.mark.parametrize("name", MODELS)
def test_models_learn_signal(name: str, tmp_path: Path) -> None:
    split = time_split(_d1(), TrainingConfig(label_delay_days=14))
    model = train_model(split, name, seed=1)  # type: ignore[arg-type]
    assert model.test["roc_auc"] > 0.6
    assert 0 <= model.test["popt"] <= 1
    assert 0 < model.threshold < 1
    assert model.meta["features"] == list(KAMEI)
    path = tmp_path / "m.pkl"
    model.save(path)
    loaded = TrainedModel.load(path)
    assert np.allclose(loaded.predict_proba(split.test), model.predict_proba(split.test))


def test_undersample_and_weights_run() -> None:
    split = time_split(_d1(), TrainingConfig(label_delay_days=14))
    under = train_model(split, "lr", imbalance="undersample")
    assert under.meta["train_positives"] * 2 == under.meta["train_rows"]
    weighted = train_model(split, "lr", imbalance="weights")
    assert weighted.meta["train_rows"] == split.train.height


def test_cli_train(tmp_path: Path) -> None:
    _d1().write_parquet(tmp_path / "d1.parquet")
    report = tmp_path / "report.json"
    cfg = tmp_path / "aegis.toml"
    cfg.write_text("[training]\nlabel_delay_days = 14\n", encoding="utf-8")
    result = CliRunner().invoke(
        app,
        [
            "train", "--repo", "r", "--model", "lightgbm", "--data", str(tmp_path),
            "--models-dir", str(tmp_path / "models"), "--report", str(report),
            "--config", str(cfg),
        ],
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    assert "lightgbm" in result.output
    assert (tmp_path / "models" / "r" / "lightgbm-none.pkl").is_file()
    data = json.loads(report.read_text("utf-8"))
    assert data["models"]["lightgbm"]["test"]["roc_auc"] > 0.5


def test_cli_train_errors(tmp_path: Path) -> None:
    runner = CliRunner()
    assert runner.invoke(app, ["train", "--repo", "r", "--data", str(tmp_path)]).exit_code == 2
    _d1().write_parquet(tmp_path / "d1.parquet")
    bad = runner.invoke(app, ["train", "--repo", "r", "--model", "svm", "--data", str(tmp_path)])
    assert bad.exit_code == 2
    missing = runner.invoke(app, ["train", "--repo", "x", "--data", str(tmp_path)])
    assert missing.exit_code == 2
    # Varsayılan 90 günlük tampon 60 günlük doğrulama dönemini boşaltır: anlaşılır hata.
    empty = runner.invoke(app, ["train", "--repo", "r", "--data", str(tmp_path)])
    assert empty.exit_code == 2 and "tampon" in empty.output
