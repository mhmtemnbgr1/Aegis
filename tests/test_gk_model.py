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
from aegis.gatekeeper.model import MODELS, TrainedModel, smote, train_model
from aegis.gatekeeper.split import time_split

START = datetime(2022, 1, 1, tzinfo=UTC)


def _d1(n: int = 400, seed: int = 0) -> pl.DataFrame:
    """Büyük ve dağınık commit'lerin daha sık hatalı olduğu sentetik D1."""
    rng = np.random.default_rng(seed)
    data: dict[str, object] = {name: rng.integers(0, 20, n).astype(float) for name in KAMEI}
    la = rng.exponential(30, n)
    nf = rng.integers(1, 8, n).astype(float)
    data["la"], data["nf"] = la, nf
    data["risky_files"] = rng.integers(0, 2, n).astype(float)
    data["test_ratio"] = rng.random(n)
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
    over = train_model(split, "lr", imbalance="smote")
    assert over.meta["train_positives"] * 2 == over.meta["train_rows"]


def test_smote_interpolates_between_minority_neighbours() -> None:
    x = np.array([[0.0, 0.0], [1.0, 1.0], [2.0, 2.0], [10.0, 0.0], [11.0, 0.0], [12.0, 0.0]])
    y = np.array([False, False, False, True, True, True])
    x = np.vstack([x, np.zeros((4, 2))])
    y = np.concatenate([y, np.zeros(4, dtype=bool)])
    xs, ys = smote(x, y, k=2, seed=1)
    assert ys.sum() == (~ys).sum() == 7
    new = xs[len(x) :]
    assert np.all((new[:, 0] >= 10) & (new[:, 0] <= 12) & (new[:, 1] == 0))
    only_clean, _ = smote(x[:3], y[:3])
    assert np.array_equal(only_clean, x[:3])


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


def test_cli_train_cross_and_general(tmp_path: Path) -> None:
    pl.concat([_d1(seed=1), _d1(seed=2).with_columns(pl.lit("o").alias("repo"))]).write_parquet(
        tmp_path / "d1.parquet"
    )
    cfg = tmp_path / "aegis.toml"
    cfg.write_text("[training]\nlabel_delay_days = 14\n", encoding="utf-8")
    common = ["--model", "lr", "--data", str(tmp_path), "--models-dir", str(tmp_path / "m")]
    common += ["--config", str(cfg)]
    report = tmp_path / "cross.json"
    cross = CliRunner().invoke(
        app, ["train", "--repo", "r", "--scenario", "cross", "--report", str(report), *common]
    )
    assert cross.exit_code == 0, cross.output
    data = json.loads(report.read_text("utf-8"))
    assert data["scenario"] == "cross"
    assert data["models"]["lr"]["train_repos"] == ["o"]
    assert (tmp_path / "m" / "r" / "lr-none-cross.pkl").is_file()
    general = CliRunner().invoke(
        app, ["train", "--repo", "all", "--report", str(tmp_path / "all.json"), *common]
    )
    assert general.exit_code == 0, general.output
    assert TrainedModel.load(tmp_path / "m" / "all" / "lr-none.pkl").meta["train_repos"] == [
        "o",
        "r",
    ]
    bad = CliRunner().invoke(app, ["train", "--repo", "all", "--scenario", "cross", *common])
    assert bad.exit_code == 2


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
