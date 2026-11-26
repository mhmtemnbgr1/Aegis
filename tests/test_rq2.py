"""RQ2 deney altyapısı: eşleşme, testler, plasebo, kaldığı yerden devam ve özet (#36).

LLM yerine sahte sağlayıcı kullanılır; bu testler deney sonucu üretmez, yalnızca altyapıyı doğrular.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from aegis.config import AegisConfig, AgentConfig
from aegis.experiments.rq2 import (
    MAX_CONSECUTIVE_ERRORS,
    done_keys,
    holm,
    load_results,
    mcnemar,
    placebo_ids,
    read_memory,
    run,
    score_sample,
    summarize,
)
from aegis.llm import LLMError, LLMProvider, MockProvider
from aegis.memory.cards import BugCard
from aegis.mining.d2 import D2Sample

BUGGY_DIFF = """\
diff --git a/geo.py b/geo.py
--- a/geo.py
+++ b/geo.py
@@ -4,3 +4,3 @@ def area(w, h):

 def perimeter(w, h):
-    return 2 * (w + h)
+    return 2 * w + h
"""  # noqa: W293
CLEAN_DIFF = """\
diff --git a/geo.py b/geo.py
--- a/geo.py
+++ b/geo.py
@@ -1,2 +1,3 @@
 def area(w, h):
+    \"\"\"Rectangle area.\"\"\"
     return w * h
"""
FINDING = {
    "file": "geo.py",
    "line": 6,
    "category": "bug",
    "severity": "high",
    "confidence": 0.9,
    "title": "Yanlış çevre formülü",
    "explanation": "parantez eksik",
    "evidence": "return 2 * w + h",
}


def _sample(label: str, sha: str, expected: list[dict[str, object]] | None = None) -> D2Sample:
    return D2Sample(
        repo="r",
        sha=sha,
        parent="p" + sha,
        label=label,
        date="2024-05-01T00:00:00+00:00",
        size_bin=0,
        src_added=1,
        files=["geo.py"],
        diff=BUGGY_DIFF if label == "buggy" else CLEAN_DIFF,
        expected=expected or [],
    )


BUGGY = _sample("buggy", "b1", [{"path": "geo.py", "line": 6}])
CLEAN = _sample("clean", "c1")


def _card(n: int, files: list[str], day: int) -> BugCard:
    return BugCard(
        id=f"BC-{n:010d}",
        fix_sha=f"{n:040d}",
        fix_date=datetime(2024, 1, day, tzinfo=UTC),
        inducing_shas=[],
        issue=None,
        files=files,
        functions=[],
        message="Fix",
        before="x = 1",
        after="x = 2",
        fix_diff="",
        summary=f"Fix {n}",
    )


def test_score_sample_tolerance_and_false_alarm() -> None:
    near = FINDING | {"line": 9}  # 3 satır uzakta: isabet
    far = FINDING | {"line": 10}
    other = FINDING | {"file": "other.py"}
    assert score_sample(BUGGY, [near, far, other]) == {
        "tp": 1,
        "findings": 3,
        "hit_lines": 1,
        "expected": 1,
        "detected": True,
    }
    assert score_sample(BUGGY, [far], tol=0)["detected"] is False
    assert score_sample(CLEAN, [FINDING]) == {"false_alarm": True, "findings": 1}
    assert score_sample(CLEAN, []) == {"false_alarm": False, "findings": 0}


def test_mcnemar_and_holm() -> None:
    a = [True] * 8 + [False] * 1 + [True] * 5
    b = [False] * 8 + [True] * 1 + [True] * 5
    only_a, only_b, p = mcnemar(a, b)
    assert (only_a, only_b) == (8, 1)
    assert abs(p - 2 * (1 + 9) / 2**9) < 1e-12  # kesin binom testi
    assert mcnemar([True], [True])[2] == 1.0
    assert holm([0.01, 0.04, 0.03]) == [0.03, 0.06, 0.06]


def test_placebo_avoids_touched_files_and_future_cards() -> None:
    cards = [
        _card(1, ["geo.py"], 1),  # örneğin dosyası
        _card(2, ["a.py"], 2),
        _card(3, ["b.py"], 3),
        _card(4, ["c.py"], 28),  # örnekten sonra düzeltilmiş
    ]
    before = datetime(2024, 1, 20, tzinfo=UTC)
    picked = placebo_ids(BUGGY, cards, 2, before)
    assert sorted(picked) == ["BC-0000000002", "BC-0000000003"]
    assert placebo_ids(BUGGY, cards, 2, before) == picked  # tohumlu, tekrarlanabilir
    assert len(placebo_ids(BUGGY, cards, 5, before)) == 2  # havuzdan fazlası istenemez


def _factory(provider: LLMProvider):  # type: ignore[no-untyped-def]
    return lambda config: provider


def test_run_resumes_and_summarizes(tmp_path: Path) -> None:
    out = tmp_path / "results.jsonl"
    card = _card(9, ["geo.py"], 1)

    def memory(sample: D2Sample, variant: str) -> list[BugCard]:
        return [card] if variant == "hybrid" else []

    # Hafızasız: bulgu yok. Hibrit: hatalı commit'te doğru bulgu, temizde yanlış alarm yok.
    responses: list[str | dict[str, object]] = [
        {"summary": "ok", "findings": []},  # b1 none
        {
            "summary": "ok",
            "findings": [FINDING | {"memory_refs": [card.id, "BC-yok"]}],
        },  # b1 hybrid
        {"summary": "ok", "findings": []},  # c1 none
        {"summary": "ok", "findings": []},  # c1 hybrid
    ]
    provider = MockProvider(responses)
    n = run(
        [BUGGY, CLEAN],
        memory,
        out,
        AegisConfig(),
        variants=["none", "hybrid"],
        provider_factory=_factory(provider),
    )
    assert n == 4 and len(provider.requests) == 4
    assert "<bug_memory>" in provider.requests[1].prompt  # hibrit varyantta kart prompt'ta
    assert "<bug_memory>" not in provider.requests[0].prompt
    rows = [json.loads(line) for line in out.read_text("utf-8").splitlines()]
    hybrid = next(r for r in rows if r["sha"] == "b1" and r["variant"] == "hybrid")
    assert hybrid["memory_cards"] == [card.id]
    assert hybrid["findings"][0]["memory_refs"] == [card.id]  # uydurma kimlik düşürüldü

    # İkinci koşu: hepsi tamam, LLM çağrılmaz.
    again = MockProvider([])
    assert run([BUGGY, CLEAN], memory, out, AegisConfig(), variants=["none", "hybrid"],
               provider_factory=_factory(again)) == 0  # fmt: skip
    assert done_keys(out) == {
        ("b1", "buggy", "none"),
        ("b1", "buggy", "hybrid"),
        ("c1", "clean", "none"),
        ("c1", "clean", "hybrid"),
    }

    scores, detect, alarm = summarize([BUGGY, CLEAN], load_results(out))
    by = {s.variant: s for s in scores}
    assert (by["hybrid"].detected, by["none"].detected) == (1, 0)
    assert by["hybrid"].precision == 1.0 and by["hybrid"].recall == 1.0
    assert by["hybrid"].false_alarms == 0 and by["hybrid"].clean == 1
    assert [d[:3] for d in detect] == [("hybrid − none", 1, 0)]
    assert alarm[0][1:3] == (0, 0)


def test_failed_runs_are_retried(tmp_path: Path) -> None:
    out = tmp_path / "results.jsonl"
    broken = MockProvider(["bu JSON değil"] * 3)
    run([BUGGY], lambda s, v: [], out, AegisConfig(), variants=["none"],
        provider_factory=_factory(broken))  # fmt: skip
    assert json.loads(out.read_text("utf-8"))["status"] == "error"
    assert done_keys(out) == set()  # hata veren koşu tekrar denenir
    fixed = MockProvider([{"summary": "ok", "findings": []}])
    assert run([BUGGY], lambda s, v: [], out, AegisConfig(), variants=["none"],
               provider_factory=_factory(fixed)) == 1  # fmt: skip
    assert load_results(out)[("b1", "buggy", "none")]["status"] == "ok"


def test_same_commit_as_buggy_and_clean_sample(tmp_path: Path) -> None:
    """Aynı commit D2'de hem hatalı (tersine çevrilmiş fix) hem temiz örnek olabilir."""
    buggy, clean = _sample("buggy", "d1", [{"path": "geo.py", "line": 6}]), _sample("clean", "d1")
    out = tmp_path / "results.jsonl"
    provider = MockProvider(
        [{"summary": "ok", "findings": [FINDING]}, {"summary": "ok", "findings": []}]
    )
    n = run([buggy, clean], lambda s, v: [], out, AegisConfig(), variants=["none"],
            provider_factory=_factory(provider))  # fmt: skip
    assert n == 2 and len(provider.requests) == 2  # ikinci örnek atlanmaz
    assert done_keys(out) == {("d1", "buggy", "none"), ("d1", "clean", "none")}
    scores, _, _ = summarize([buggy, clean], load_results(out))
    assert (scores[0].samples, scores[0].detected, scores[0].false_alarms) == (2, 1, 0)


def test_read_memory_keeps_cards_apart_for_same_commit(tmp_path: Path) -> None:
    a, b = _card(1, ["a.py"], 1), _card(2, ["b.py"], 2)
    cards = tmp_path / "cards.jsonl"
    cards.write_text(a.model_dump_json() + "\n" + b.model_dump_json() + "\n", "utf-8")
    buggy, clean = _sample("buggy", "d1"), _sample("clean", "d1")

    # Eski biçim: etiket alanı yok, satırlar D2 sırasıyla eşlenir.
    old = tmp_path / "old.jsonl"
    old.write_text(
        json.dumps({"repo": "r", "sha": "d1", "modes": {"hybrid": [a.id]}}) + "\n"
        + json.dumps({"repo": "r", "sha": "d1", "modes": {"hybrid": [b.id]}}) + "\n",
        "utf-8",
    )  # fmt: skip
    get = read_memory(old, cards, [buggy, clean])
    assert [c.id for c in get(buggy, "hybrid")] == [a.id]
    assert [c.id for c in get(clean, "hybrid")] == [b.id]

    # Yeni biçim: satırda etiket var, sıra gerekmez.
    new = tmp_path / "new.jsonl"
    new.write_text(
        json.dumps({"sha": "d1", "label": "clean", "modes": {"hybrid": [b.id]}}) + "\n"
        + json.dumps({"sha": "d1", "label": "buggy", "modes": {"hybrid": [a.id]}}) + "\n",
        "utf-8",
    )  # fmt: skip
    get = read_memory(new, cards)
    assert [c.id for c in get(buggy, "hybrid")] == [a.id]
    assert [c.id for c in get(clean, "hybrid")] == [b.id]

    with pytest.raises(ValueError):
        read_memory(old, cards, [clean])  # sıra D2 ile uyuşmuyor


def test_rows_record_context_and_old_rows_are_ignored(tmp_path: Path) -> None:
    out = tmp_path / "results.jsonl"
    # İlk koşunun satırı: bağlam penceresi kaydı yok (istemler kesilmişti).
    old = {"sha": "b1", "label": "buggy", "variant": "none", "status": "ok", "findings": []}
    out.write_text(json.dumps(old) + "\n", "utf-8")
    assert done_keys(out) == set() and load_results(out) == {}

    config = AegisConfig(agents={"analyst": AgentConfig(num_ctx=16384, temperature=0.0)})
    provider = MockProvider([{"summary": "ok", "findings": []}])
    assert run([BUGGY], lambda s, v: [], out, config, variants=["none"],
               provider_factory=_factory(provider)) == 1  # fmt: skip
    row = load_results(out)[("b1", "buggy", "none")]
    assert (row["num_ctx"], row["temperature"]) == (16384, 0.0)
    assert done_keys(out) == {("b1", "buggy", "none")}


def test_run_stops_after_consecutive_errors(tmp_path: Path) -> None:
    out = tmp_path / "results.jsonl"
    samples = [_sample("buggy", f"s{i}") for i in range(MAX_CONSECUTIVE_ERRORS + 5)]

    class Down:
        name, model = "ollama", "q"

        def complete(self, request: object) -> None:
            raise LLMError("ollama: bağlantı yok", retryable=False)

    broken = Down()  # her çağrı hata verir (ör. Ollama kapalı)
    with pytest.raises(RuntimeError, match="art arda"):
        run(samples, lambda s, v: [], out, AegisConfig(), variants=["none"],
            provider_factory=_factory(broken))  # fmt: skip
    assert len(out.read_text("utf-8").splitlines()) == MAX_CONSECUTIVE_ERRORS
