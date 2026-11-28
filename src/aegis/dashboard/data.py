"""Dashboard veri katmanı (FR-60 – FR-66).

Yalnızca okur: depodaki veri setleri (`eval/datasets/`), deney sonuçları (`eval/results/`) ve
yereldeki çalıştırma kayıtları (`.aegis/runs.jsonl`). Streamlit'e bağımlı değildir; ekranlar
(`app.py`) bu fonksiyonları çağırır, testler de doğrudan bunları sınar.
"""

import json
import math
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from aegis.experiments.rq1 import TriageSample, key, read_samples, recall_at
from aegis.memory.cards import BugCard, read_cards

DATASETS = Path("eval/datasets")
RESULTS = Path("eval/results")
RUNS = Path(".aegis/runs.jsonl")
LLM_BANDS = ("medium", "high")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


# --- Genel bakış: çalıştırma kayıtları ---------------------------------------------------------
def load_runs(paths: Iterable[Path]) -> list[dict[str, Any]]:
    """D4 ve yerel kayıtlar; aynı `run_id` bir kez sayılır, en yeni en üstte."""
    runs: dict[str, dict[str, Any]] = {}
    for path in paths:
        for row in read_jsonl(path):
            runs.setdefault(str(row.get("run_id")), row)
    return sorted(runs.values(), key=lambda r: str(r.get("started_at", "")), reverse=True)


def run_totals(runs: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Özet kutuları: çalıştırma ve PR sayısı, LLM'e yönlendirilen pay, bulgular, süre."""
    prs = {(r.get("repo"), r.get("pr")) for r in runs if r.get("pr") is not None}
    routed = sum(r.get("risk_band") in LLM_BANDS for r in runs)
    return {
        "runs": len(runs),
        "prs": len(prs),
        "llm_share": routed / len(runs) if runs else 0.0,
        "findings": sum(int(r.get("findings") or 0) for r in runs),
        "tokens": sum(
            int(r.get("input_tokens") or 0) + int(r.get("output_tokens") or 0) for r in runs
        ),
        "mean_seconds": (
            sum(float(r.get("duration_seconds") or 0) for r in runs) / len(runs) if runs else 0.0
        ),
        "bands": dict(Counter(str(r.get("risk_band")) for r in runs)),
        "statuses": dict(Counter(str(r.get("status")) for r in runs)),
    }


# --- Gatekeeper: maliyet-recall eğrisi -----------------------------------------------------------
def triage_samples(datasets: Path = DATASETS) -> list[TriageSample]:
    path = datasets / "rq1-triage.jsonl"
    return read_samples(path) if path.is_file() else []


def llm_triage_scores(results: Path = RESULTS) -> dict[str, dict[str, float]]:
    """`eval/results/rq1-triage/<model>/results.jsonl` → model → (PR anahtarı → risk)."""
    out: dict[str, dict[str, float]] = {}
    for path in sorted((results / "rq1-triage").glob("*/results.jsonl")):
        risks = {
            r["pr_key"]: float(r["risk"]) for r in read_jsonl(path) if r.get("risk") is not None
        }
        if risks:
            out[f"LLM ({path.parent.name.replace('_', ':', 1)})"] = risks
    return out


def cost_recall(
    samples: Sequence[TriageSample],
    shares: Sequence[float],
    extra: dict[str, dict[str, float]] | None = None,
    repos: Iterable[str] | None = None,
) -> dict[str, list[float]]:
    """Yöntem → her pay için yakalanan hatalı PR oranı (pencere ortalaması).

    RQ1 ile aynı yöntem (`aegis.experiments.rq1`): her (repo, pencere) içinde skoru en yüksek
    `pay` kadar PR LLM'e gider; recall pencerelerin ortalamasıdır. Ek yöntemler (LLM triage)
    yalnızca yanıtladıkları PR'larda karşılaştırılır, bu yüzden o durumda tüm yöntemler aynı
    PR alt kümesinde ölçülür.
    """
    extra = extra or {}
    wanted = set(repos) if repos is not None else None
    pool = [
        s
        for s in samples
        if (wanted is None or s.repo in wanted) and all(key(s) in m for m in extra.values())
    ]
    groups: dict[tuple[str, int], list[TriageSample]] = {}
    for s in pool:
        groups.setdefault((s.repo, s.window), []).append(s)
    methods: dict[str, list[list[float]]] = {
        name: [[] for _ in shares] for name in ("Risk modeli (LR)", "Sezgisel kural", *extra)
    }
    for group in groups.values():
        y = np.array([s.buggy for s in group])
        if not y.any():
            continue
        scores = {
            "Risk modeli (LR)": np.array([s.lr for s in group]),
            "Sezgisel kural": np.array([s.heuristic for s in group]),
            **{name: np.array([m[key(s)] for s in group]) for name, m in extra.items()},
        }
        for name, score in scores.items():
            for i, share in enumerate(shares):
                methods[name][i].append(recall_at(y, score, share))
    return {
        name: [float(np.mean(v)) if v else math.nan for v in per_share]
        for name, per_share in methods.items()
    }


# --- Hafıza: hata kartları -----------------------------------------------------------------------
@dataclass
class CardEntry:
    repo: str
    card: BugCard


def load_cards(datasets: Path = DATASETS, state: Path = Path(".aegis/data")) -> list[CardEntry]:
    """Depodaki D2 kartları ve (varsa) yerel durum arşivindeki tüm kartlar.

    D2 kart dosyalarında repo alanı yoktur; repo, kartı kullanan hafıza satırlarından bulunur.
    """
    owner: dict[str, str] = {}
    for name in ("d2-memory.jsonl", "d2-szz-memory.jsonl"):
        for row in read_jsonl(datasets / name):
            for ids in row.get("modes", {}).values():
                for card_id in ids:
                    owner.setdefault(card_id, row["repo"])
    entries: dict[str, CardEntry] = {}
    for path in sorted(state.glob("*/cards.jsonl")) if state.is_dir() else []:
        for card in read_cards(path):
            entries.setdefault(card.id, CardEntry(path.parent.name, card))
    for name in ("d2-cards.jsonl", "d2-szz-cards.jsonl"):
        for card in read_cards(datasets / name):
            entries.setdefault(card.id, CardEntry(owner.get(card.id, "bilinmiyor"), card))
    return sorted(entries.values(), key=lambda e: e.card.fix_date, reverse=True)


def _haystack(entry: CardEntry) -> str:
    card = entry.card
    issue = f"#{card.issue.number} {card.issue.title or ''}" if card.issue else ""
    return " ".join([card.id, card.fix_sha, *card.files, *card.functions, card.summary, issue])


def search_cards(
    entries: Sequence[CardEntry], query: str, repo: str | None = None, limit: int | None = None
) -> list[CardEntry]:
    """Kimlik, dosya, fonksiyon, özet ve issue üzerinde arama; tüm kelimeler geçmeli."""
    words = query.lower().split()
    hits = [
        e
        for e in entries
        if (repo is None or e.repo == repo) and all(w in _haystack(e).lower() for w in words)
    ]
    return hits if limit is None else hits[:limit]


# --- Deneyler: üretilmiş özetler -----------------------------------------------------------------
def result_summaries(results: Path = RESULTS, docs: Path = Path("docs")) -> dict[str, Path]:
    """Başlık → Markdown özeti (`docs/results.md` ve `eval/results/**/summary.md`)."""
    out: dict[str, Path] = {}
    if (docs / "results.md").is_file():
        out["LLM'siz sonuçlar (docs/results.md)"] = docs / "results.md"
    for path in sorted(results.glob("*/*/summary.md")):
        out[f"{path.parent.parent.name} / {path.parent.name}"] = path
    return out
