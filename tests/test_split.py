"""Zaman sıralı bölme ve etiket gecikmesi (#14)."""

from datetime import UTC, datetime, timedelta

import polars as pl
import pytest

from aegis.config import TrainingConfig, parse_config
from aegis.gatekeeper.split import labels_as_of, time_split

START = datetime(2024, 1, 1, tzinfo=UTC)


def _d1(n: int = 100, fixes: dict[int, int] | None = None) -> pl.DataFrame:
    """Günde bir commit; `fixes`: commit sırası → kaç gün sonra düzeltildiği."""
    fixes = fixes or {}
    return pl.DataFrame(
        {
            "sha": [f"c{i:03d}" for i in range(n)],
            "as_of": [START + timedelta(days=i) for i in range(n)],
            "la": [float(i) for i in range(n)],
            "fixed_at": [
                START + timedelta(days=i + fixes[i]) if i in fixes else None for i in range(n)
            ],
        },
        schema_overrides={"fixed_at": pl.Datetime("us", "UTC")},
    ).with_columns(pl.col("fixed_at").is_not_null().alias("buggy"))


def test_sets_are_time_ordered_and_disjoint() -> None:
    split = time_split(
        _d1().sample(fraction=1, shuffle=True, seed=1), TrainingConfig(label_delay_days=0)
    )
    train, valid, test = split.train, split.valid, split.test
    assert (train.height, valid.height, test.height) == (65, 15, 20)
    assert train["as_of"].max() < valid["as_of"].min()
    assert valid["as_of"].max() < test["as_of"].min()
    assert not set(train["sha"]) & set(valid["sha"]) | set(train["sha"]) & set(test["sha"])


def test_label_delay_buffer_drops_recent_commits() -> None:
    split = time_split(_d1(), TrainingConfig(label_delay_days=10))
    # Doğrulama 65. günde başlıyor: eğitim 55. günden önce biter.
    assert split.train["as_of"].max() == START + timedelta(days=54)
    # Test 80. günde başlıyor: doğrulama 70. günden önce biter.
    assert split.valid["as_of"].max() == START + timedelta(days=69)
    assert split.test.height == 20  # test kümesinde tampon yok


def test_future_fixes_do_not_leak_into_training_labels() -> None:
    # c010 5 gün sonra düzeltilmiş (eğitim sırasında biliniyor);
    # c020 200 gün sonra düzeltilmiş (eğitim ve doğrulama anında henüz bilinmiyor).
    split = time_split(_d1(fixes={10: 5, 20: 200, 90: 1}), TrainingConfig(label_delay_days=0))
    train = dict(zip(split.train["sha"], split.train["buggy"], strict=True))
    assert train["c010"] is True
    assert train["c020"] is False
    # Test kümesi son etiketi kullanır.
    assert split.test.filter(pl.col("sha") == "c090")["buggy"].item() is True


def test_adding_future_commits_keeps_training_rows_and_labels() -> None:
    cfg = TrainingConfig(label_delay_days=0)
    base = time_split(_d1(fixes={10: 5, 20: 30}), cfg)
    # Aynı geçmiş + aynı bölme sınırları; sonradan bulunan hatalar eğitim etiketini değiştirmemeli.
    later = labels_as_of(_d1(fixes={10: 5, 20: 30, 30: 400}), base.valid_start).filter(
        pl.col("as_of") < base.valid_start
    )
    assert later.select("sha", "buggy").equals(base.train.select("sha", "buggy"))


def test_config_from_toml_and_validation() -> None:
    cfg = parse_config("[training]\nlabel_delay_days = 30\ntest_fraction = 0.3\n").training
    assert (cfg.label_delay_days, cfg.test_fraction) == (30, 0.3)
    with pytest.raises(ValueError, match="1'den küçük"):
        TrainingConfig(valid_fraction=0.5, test_fraction=0.5)
    with pytest.raises(ValueError, match="en az 3"):
        time_split(_d1(2))
    with pytest.raises(ValueError, match="tampon"):
        time_split(_d1(), TrainingConfig(label_delay_days=30))  # doğrulama 15 gün
