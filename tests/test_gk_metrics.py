"""Efora duyarlı metrikler, elle hesaplanmış örneklerle (#15)."""

import math

import pytest

from aegis.gatekeeper.metrics import best_f1_threshold, evaluate, popt, recall_at_effort

# 5 commit: efor (değişen satır) ve gerçek etiket.
EFFORT = [10, 10, 40, 20, 20]  # toplam 100
BUGGY = [1, 0, 1, 0, 0]


def test_recall_at_effort_hand_computed() -> None:
    # Skorlar → yoğunluk (skor/efor): c0 .09, c1 .08, c2 .02, c3 .01, c4 .005
    score = [0.9, 0.8, 0.8, 0.2, 0.1]
    # Sıra c0, c1, c2…: c0+c1 = 20 efor = %20 bütçe; c0 hatalı → 1/2 hata bulundu.
    assert recall_at_effort(BUGGY, score, EFFORT) == pytest.approx(0.5)
    # Bütçe %60: c0, c1, c2 incelenir (60) → 2/2.
    assert recall_at_effort(BUGGY, score, EFFORT, budget=0.6) == pytest.approx(1.0)


def test_popt_bounds() -> None:
    # En iyi sıralama: gerçek yoğunluk (c0 = 0.1, c2 = 0.025) önde → Popt = 1.
    perfect = [1.0, 0.0, 1.0, 0.0, 0.0]
    assert popt(BUGGY, [p * 1000 for p in perfect], EFFORT) == pytest.approx(1.0)
    # En kötü sıralama: önce temizler (c1, c3, c4), sonra düşük yoğunluklu hata c2, en son c0.
    # Yoğunluklar (skor/efor): c1 1.0, c3 0.5, c4 0.4, c2 0.01, c0 0.001 → Popt = 0.
    worst = [0.01, 10.0, 0.4, 10.0, 8.0]
    assert popt(BUGGY, worst, EFFORT) == pytest.approx(0.0)
    # Arada bir sıralama 0 ile 1 arasında kalır.
    assert 0 < popt(BUGGY, [0.9, 0.8, 0.8, 0.2, 0.1], EFFORT) < 1


def test_undefined_without_positives() -> None:
    assert math.isnan(recall_at_effort([0, 0], [0.1, 0.2], [1, 1]))
    assert math.isnan(popt([0, 0], [0.1, 0.2], [1, 1]))
    metrics = evaluate([0, 0], [0.1, 0.9], [1, 1])
    assert math.isnan(metrics["roc_auc"]) and math.isnan(metrics["mcc"])


def test_evaluate_and_threshold() -> None:
    y = [0, 0, 1, 1]
    prob = [0.1, 0.4, 0.35, 0.8]
    m = evaluate(y, prob, [1, 1, 1, 1], threshold=0.35)
    assert m["roc_auc"] == pytest.approx(0.75)
    assert m["f1"] == pytest.approx(0.8)  # tahmin: 0,1,1,1 → TP 2, FP 1
    assert (m["positives"], m["n"]) == (2, 4)
    assert best_f1_threshold(y, prob) == pytest.approx(0.35)
