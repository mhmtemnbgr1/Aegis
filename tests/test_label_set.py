import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))

from label_set import summary, verified_label, wilson  # noqa: E402


def test_wilson_interval() -> None:
    lo, hi = wilson(8, 10)
    assert round(lo, 3) == 0.490 and round(hi, 3) == 0.943
    assert all(math.isnan(x) for x in wilson(0, 0))
    lo, hi = wilson(0, 20)
    assert abs(lo) < 1e-12 and round(hi, 3) == 0.161


def test_verified_label() -> None:
    assert verified_label("szz", "dogru") == "buggy"
    assert verified_label("szz", "kismen") == "buggy"
    assert verified_label("szz", "yanlis") == ""  # başka bir hatayı getiriyor olabilir
    assert verified_label("clean", "temiz") == "clean"
    assert verified_label("clean", "hatali") == "buggy"
    assert verified_label("fix", "evet") == ""  # commit etiketi değil, D2 örneğini doğrular
    assert verified_label("clean", "belirsiz") == ""


def test_summary_counts_exclude_uncertain() -> None:
    rows = [
        {"kind": "szz", "repo": "a", "answer": "dogru"},
        {"kind": "szz", "repo": "a", "answer": "yanlis"},
        {"kind": "szz", "repo": "b", "answer": "kismen"},
        {"kind": "szz", "repo": "b", "answer": "belirsiz"},
        {"kind": "fix", "repo": "a", "answer": "evet"},
        {"kind": "clean", "repo": "a", "answer": "temiz"},
        {"kind": "clean", "repo": "b", "answer": "hatali"},
    ]
    text = "\n".join(summary(rows))
    assert "| SZZ hatalı commit | doğru | 1/3 = %33,3" in text
    assert "| SZZ hatalı commit | doğru + kısmen | 2/3 = %66,7" in text
    assert "gerçek düzeltme | 1/1 = %100,0" in text
    assert "| Temiz commit | temiz | 1/2 = %50,0" in text
    assert "| a | 1/2 = %50,0" in text and "| b | 1/1 = %100,0" in text
