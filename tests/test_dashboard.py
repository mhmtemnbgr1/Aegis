"""Dashboard veri katmanı: kayıtlar, maliyet-recall eğrisi, kart araması ve özetler.

Streamlit ekranları test edilmez; ekranların okuduğu her şey `aegis.dashboard.data` içindedir.
"""

import json
import math
from datetime import UTC, datetime
from pathlib import Path

from aegis.dashboard import data
from aegis.experiments.rq1 import TriageSample
from aegis.memory.cards import BugCard, Issue


def _write(path: Path, rows: list[dict[str, object]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), "utf-8")
    return path


def _run(run_id: str, band: str, started: str, **extra: object) -> dict[str, object]:
    return {
        "run_id": run_id,
        "started_at": started,
        "risk_band": band,
        "status": "ok",
        "findings": 1,
        "input_tokens": 100,
        "output_tokens": 10,
        "duration_seconds": 2.0,
        **extra,
    }


def test_runs_are_deduplicated_and_summarised(tmp_path: Path) -> None:
    d4 = _write(
        tmp_path / "d4.jsonl",
        [
            _run("a", "low", "2026-11-01T10:00:00", repo="o/r", pr=1, findings=0),
            _run("b", "high", "2026-11-02T10:00:00", repo="o/r", pr=2),
        ],
    )
    local = _write(
        tmp_path / "runs.jsonl",
        [_run("b", "high", "2026-11-02T10:00:00"), _run("c", "medium", "2026-11-03T10:00:00")],
    )
    runs = data.load_runs([d4, local, tmp_path / "yok.jsonl"])
    assert [r["run_id"] for r in runs] == ["c", "b", "a"]  # tekrar yok, en yeni üstte
    totals = data.run_totals(runs)
    assert (totals["runs"], totals["prs"], totals["findings"]) == (3, 2, 2)
    assert totals["llm_share"] == 2 / 3
    assert totals["tokens"] == 330 and totals["mean_seconds"] == 2.0
    assert totals["bands"] == {"high": 1, "low": 1, "medium": 1}
    assert data.run_totals([])["llm_share"] == 0.0


def _triage(repo: str, window: int, pr: int, buggy: bool, lr: float, h: float) -> TriageSample:
    return TriageSample(repo, window, str(pr), f"sha{pr}", buggy, "", False, lr, h)


def test_cost_recall_matches_rq1_method() -> None:
    samples = [
        # Pencere 1: LR hatalıyı en üste koyar, sezgisel kural en alta.
        _triage("r1", 0, 1, True, 0.9, 0.1),
        _triage("r1", 0, 2, False, 0.2, 0.8),
        _triage("r1", 0, 3, False, 0.1, 0.5),
        _triage("r1", 0, 4, False, 0.0, 0.4),
        # Pencere 2: hatalı PR yok, ortalamaya girmez.
        _triage("r2", 0, 5, False, 0.5, 0.5),
    ]
    curve = data.cost_recall(samples, [0.25, 1.0])
    assert curve["Risk modeli (LR)"] == [1.0, 1.0]
    assert curve["Sezgisel kural"] == [0.0, 1.0]
    assert all(
        math.isnan(v) for v in data.cost_recall(samples, [0.25], repos=["r2"])["Sezgisel kural"]
    )

    # LLM triage yalnızca yanıtladığı PR'larda; diğer yöntemler de aynı alt kümede ölçülür.
    llm = {"LLM (m)": {"r1#1": 0.3, "r1#2": 0.9}}
    curve = data.cost_recall(samples, [0.5], llm)
    assert curve == {"Risk modeli (LR)": [1.0], "Sezgisel kural": [0.0], "LLM (m)": [0.0]}


def test_llm_triage_scores_skip_failed_rows(tmp_path: Path) -> None:
    _write(
        tmp_path / "rq1-triage" / "qwen2.5-coder_1.5b" / "results.jsonl",
        [{"pr_key": "r#1", "risk": 0.4}, {"pr_key": "r#2", "risk": None}],
    )
    assert data.llm_triage_scores(tmp_path) == {"LLM (qwen2.5-coder:1.5b)": {"r#1": 0.4}}
    assert data.llm_triage_scores(tmp_path / "yok") == {}


def _card(n: int, files: list[str], functions: list[str], summary: str, day: int) -> BugCard:
    return BugCard(
        id=f"BC-{n:010d}",
        fix_sha=f"{n:040d}",
        fix_date=datetime(2024, 1, day, tzinfo=UTC),
        inducing_shas=[],
        issue=Issue(number=80 + n, title="Leak"),
        files=files,
        functions=functions,
        message="",
        before="",
        after="",
        fix_diff="",
        summary=summary,
    )


def test_cards_get_their_repo_and_can_be_searched(tmp_path: Path) -> None:
    pool = _card(
        1, ["app/db/pool.py"], ["app.db.pool.ConnectionPool.release"], "Release on timeout", 5
    )
    web = _card(2, ["web/app.py"], ["web.app.route"], "Fix route", 9)
    datasets = tmp_path / "datasets"
    _write(datasets / "d2-cards.jsonl", [json.loads(pool.model_dump_json())])
    _write(
        datasets / "d2-memory.jsonl",
        [{"repo": "o__db", "sha": "x", "modes": {"hybrid": [pool.id]}}],
    )
    state = tmp_path / "state"
    _write(state / "o__web" / "cards.jsonl", [json.loads(web.model_dump_json())])

    entries = data.load_cards(datasets, state)
    assert [(e.card.id, e.repo) for e in entries] == [(web.id, "o__web"), (pool.id, "o__db")]
    assert [e.card.id for e in data.search_cards(entries, "pool.py")] == [pool.id]
    assert [e.card.id for e in data.search_cards(entries, "connectionpool TIMEOUT")] == [pool.id]
    assert [e.card.id for e in data.search_cards(entries, "#81")] == [pool.id]
    assert data.search_cards(entries, "pool.py route") == []  # tüm kelimeler geçmeli
    assert [e.card.id for e in data.search_cards(entries, "", repo="o__web")] == [web.id]
    assert len(data.search_cards(entries, "", limit=1)) == 1
    assert data.load_cards(tmp_path / "yok", tmp_path / "yok") == []


def test_result_summaries(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "results.md").write_text("# Sonuçlar\n", "utf-8")
    summary = tmp_path / "results" / "rq2" / "qwen2.5-coder_7b" / "summary.md"
    summary.parent.mkdir(parents=True)
    summary.write_text("# RQ2\n", "utf-8")
    assert data.result_summaries(tmp_path / "results", docs) == {
        "LLM'siz sonuçlar (docs/results.md)": docs / "results.md",
        "rq2 / qwen2.5-coder_7b": summary,
    }
