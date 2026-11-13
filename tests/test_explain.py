"""Skor açıklamaları (#19)."""

import numpy as np
import pytest

from aegis.config import TrainingConfig
from aegis.features.kamei import KAMEI
from aegis.gatekeeper.explain import TEXT, Explanation, contributions, explain
from aegis.gatekeeper.model import MODELS, train_model
from aegis.gatekeeper.split import time_split
from tests.test_gk_model import _d1


@pytest.fixture(scope="module")
def split():  # type: ignore[no-untyped-def]
    return time_split(_d1(600, seed=4), TrainingConfig(label_delay_days=14))


@pytest.mark.parametrize("name", MODELS)
def test_contributions_add_up_to_model_output(name: str, split) -> None:  # type: ignore[no-untyped-def]
    model = train_model(split, name, calibration="none", seed=0)  # type: ignore[arg-type]
    phi, base = contributions(model, split.test)
    total = phi.sum(axis=1) + base
    raw = model.raw_proba(split.test)
    if name == "rf":
        assert np.allclose(total, raw, atol=1e-6)
    else:
        assert np.allclose(1 / (1 + np.exp(-total)), raw, atol=1e-6)


@pytest.mark.parametrize("name", MODELS)
def test_signal_features_rank_high(name: str, split) -> None:  # type: ignore[no-untyped-def]
    # Sentetik veride risk yalnızca la ve nf'ye bağlı.
    model = train_model(split, name, seed=0)  # type: ignore[arg-type]
    phi, _ = contributions(model, split.test)
    importance = np.abs(phi).mean(axis=0)
    top2 = {list(KAMEI)[i] for i in np.argsort(-importance)[:2]}
    assert top2 == {"la", "nf"}


def test_explain_top3_and_text(split) -> None:  # type: ignore[no-untyped-def]
    model = train_model(split, "lr", seed=0)
    rows = explain(model, split.test.head(5))
    assert len(rows) == 5 and all(len(r) == 3 for r in rows)
    first = rows[0]
    assert abs(first[0].effect) >= abs(first[1].effect) >= abs(first[2].effect)
    pr = model.explain_pr(split.test.head(4))
    assert 0 < len(pr) <= 3 and all(e.effect > 0 for e in pr)
    assert all(isinstance(e, Explanation) for e in pr)
    assert [e.effect for e in pr] == sorted((e.effect for e in pr), reverse=True)
    assert model.explain_pr(split.test.head(0)) == []


def test_every_feature_has_turkish_text() -> None:
    assert set(TEXT) == set(KAMEI) | {"risky_files", "test_ratio", "n_commits", "n_authors"}
    assert Explanation("la", 1234, 0.4).text == "1.234 satır eklendi (riski artırıyor)"
    assert Explanation("fix", 1, -0.1).text == "değişiklik bir hata düzeltmesi (riski azaltıyor)"
    for name in KAMEI:
        assert Explanation(name, 3.0, 1.0).text
