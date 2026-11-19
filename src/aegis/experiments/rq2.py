"""RQ2: hafıza varyantlarının D2 üzerinde karşılaştırılması (#36).

Üç adım:

1. `prepare_memory` (LLM'siz, madencilik verisi ve klonlarla): her D2 örneği için hafızadan
   getirilen kartlar. Varyantlar: `structural`, `vector`, `hybrid` (gerçek arama, örneğin tarihinden
   önce düzeltilmiş kartlar) ve `placebo` (aynı repodan, örneğin dosyalarına dokunmayan, aynı sayıda
   rastgele kart). Sonuç `d2-memory.jsonl` ve gereken kartlar `d2-cards.jsonl` olarak yazılır.
2. `run` (Ollama ile): her örnek × varyant için `run_review`; sonuçlar JSONL'e eklenir, yarıda
   kalan koşu kaldığı yerden devam eder. Risk, tüm örneklerde sabit (orta) verilir: RQ2 yalnızca
   hafızanın etkisini ölçer, gatekeeper'ı değil.
3. `summarize`: satır düzeyinde precision/recall/F1, hatalı commit'lerde tespit oranı, temiz
   commit'lerde yanlış alarm oranı; varyantlar arası McNemar testleri (Holm düzeltmesi).
"""

import json
import math
import random
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aegis.config import AegisConfig
from aegis.diff.models import Diff
from aegis.gatekeeper.base import RiskAssessment, RiskBand
from aegis.memory.cards import BugCard, read_cards
from aegis.mining.d2 import D2Sample

VARIANTS = ("none", "placebo", "structural", "vector", "hybrid")
DEFAULT_VARIANTS = ("none", "placebo", "vector", "hybrid")
LINE_TOLERANCE = 3
"""Bir bulgu, beklenen satırdan en çok bu kadar uzaktaysa (aynı dosyada) isabet sayılır."""


class FixedRisk:
    """Her örneğe aynı risk; LLM'in bağlamı varyantlar arasında yalnızca hafızada farklıdır."""

    def assess(self, diff: Diff, *, as_of: datetime) -> RiskAssessment:
        return RiskAssessment(score=0.5, band=RiskBand.MEDIUM, reasons=[], source="experiment")


# --- 1. Hazırlık -----------------------------------------------------------------------------
def placebo_ids(
    sample: D2Sample, cards: Sequence[BugCard], count: int, before: datetime, seed: int = 0
) -> list[str]:
    """Aynı repodan, örneğin dosyalarına dokunmayan, ondan önce düzeltilmiş rastgele kartlar."""
    touched = set(sample.files)
    pool = sorted(
        (c for c in cards if c.fix_date < before and not touched.intersection(c.files)),
        key=lambda c: c.id,
    )
    rng = random.Random(f"{seed}:{sample.sha}")
    return [c.id for c in rng.sample(pool, min(count, len(pool)))]


def prepare_memory(
    samples: Iterable[D2Sample],
    data_root: Path,
    clone_root: Path,
    index_root: Path,
    memory_out: Path,
    cards_out: Path,
    *,
    config: AegisConfig | None = None,
    seed: int = 0,
) -> dict[str, int]:
    """Her örnek için varyant → kart kimlikleri; kullanılan kartlar ayrı dosyaya."""
    from aegis.memory.retrieve import Retriever, query_from_diff, query_from_range
    from aegis.mining.gitfiles import git

    config = config or AegisConfig()
    k = config.memory.top_k
    retrievers: dict[str, Retriever] = {}
    used: dict[str, BugCard] = {}
    rows: list[dict[str, Any]] = []
    for s in samples:
        if s.repo not in retrievers:
            retrievers[s.repo] = Retriever.load(
                data_root / s.repo / "cards.jsonl", index_root / s.repo
            )
        retriever = retrievers[s.repo]
        repo = clone_root / s.repo
        when = datetime.fromisoformat(git(repo, "log", "-1", "--format=%cI", s.sha).strip())
        if s.revert:
            # Tersine çevrilmiş düzeltme: sorgu fix → ebeveyn diff'inden. Fix'in kendi kartı tarih
            # filtresiyle zaten dışarıda (kart tarihi = fix'in commit tarihi); ayrıca açıkça atılır.
            query = query_from_diff(repo, s.sha, s.parent, config, before=when)
        else:
            query = query_from_range(repo, s.parent, s.sha, config, before=when)
        own = {c.id for c in retriever.cards if c.fix_sha == s.sha}
        modes: dict[str, list[str]] = {"none": []}
        for mode in ("structural", "vector", "hybrid"):
            hits = retriever.search(query, k=k + len(own), mode=mode)
            modes[mode] = [h.card_id for h in hits if h.card_id not in own][:k]
        modes["placebo"] = placebo_ids(s, retriever.cards, len(modes["hybrid"]) or k, when, seed)
        for ids in modes.values():
            for card_id in ids:
                used.setdefault(card_id, retriever.card(card_id))
        rows.append({"repo": s.repo, "sha": s.sha, "before": when.isoformat(), "modes": modes})
    memory_out.parent.mkdir(parents=True, exist_ok=True)
    with memory_out.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    with cards_out.open("w", encoding="utf-8", newline="\n") as fh:
        for card in sorted(used.values(), key=lambda c: c.id):
            fh.write(slim(card).model_dump_json() + "\n")
    return {
        "samples": len(rows),
        "cards": len(used),
        **{f"empty_{m}": sum(not r["modes"][m] for r in rows) for m in VARIANTS[1:]},
    }


def slim(card: BugCard) -> BugCard:
    """Prompt'a girmeyen alanlar boşaltılır (`render_card`: fix_diff yalnız `before` boşsa)."""
    update: dict[str, Any] = {"message": "", "inducing_shas": []}
    if card.before:
        update["fix_diff"] = ""
    return card.model_copy(update=update)


def read_memory(memory_path: Path, cards_path: Path) -> Callable[[str, str], list[BugCard]]:
    """(sha, varyant) → kartlar."""
    cards = {c.id: c for c in read_cards(cards_path)}
    modes: dict[str, dict[str, list[str]]] = {}
    with memory_path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                row = json.loads(line)
                modes[row["sha"]] = row["modes"]

    def get(sha: str, variant: str) -> list[BugCard]:
        return [cards[i] for i in modes.get(sha, {}).get(variant, [])]

    return get


# --- 2. Koşu ---------------------------------------------------------------------------------
def done_keys(results: Path) -> set[tuple[str, str]]:
    """Daha önce tamamlanmış (sha, varyant) çiftleri; hata veren koşular yeniden denenir."""
    keys: set[tuple[str, str]] = set()
    if results.is_file():
        with results.open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    row = json.loads(line)
                    if row["status"] != "error":
                        keys.add((row["sha"], row["variant"]))
    return keys


def run(
    samples: Sequence[D2Sample],
    memory: Callable[[str, str], list[BugCard]],
    results: Path,
    config: AegisConfig,
    *,
    variants: Sequence[str] = DEFAULT_VARIANTS,
    provider_factory: Any = None,
    on_result: Callable[[dict[str, Any]], None] | None = None,
) -> int:
    """Eksik (örnek, varyant) çiftlerini koşturur ve `results`'a ekler; koşulan sayıyı döndürür."""
    from aegis.review import ReviewStatus, run_review

    done = done_keys(results)
    results.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    kwargs: dict[str, Any] = {}
    if provider_factory is not None:
        kwargs["provider_factory"] = provider_factory
    with results.open("a", encoding="utf-8", newline="\n") as fh:
        for s in samples:
            for variant in variants:
                if (s.sha, variant) in done:
                    continue
                cards = memory(s.sha, variant)

                def source(c: list[BugCard] = cards) -> list[BugCard]:
                    return c

                started = time.perf_counter()
                review = run_review(
                    s.diff,
                    config,
                    as_of=datetime.fromisoformat(s.date),
                    gatekeeper=FixedRisk(),
                    memory=source if variant != "none" else None,
                    **kwargs,
                )
                ok = review.status is ReviewStatus.OK
                row = {
                    "repo": s.repo,
                    "sha": s.sha,
                    "label": s.label,
                    "variant": variant,
                    "status": "ok" if ok else "error",
                    "error": review.error,
                    "model": review.model,
                    "prompt_version": review.prompt_version,
                    "memory_cards": review.memory_cards,
                    "findings": [
                        {
                            "file": f.file,
                            "line": f.line,
                            "end_line": f.end_line,
                            "category": str(f.category),
                            "severity": str(f.severity),
                            "confidence": f.confidence,
                            "title": f.title,
                            "memory_refs": f.memory_refs,
                        }
                        for f in review.findings
                    ],
                    "dropped": len(review.dropped),
                    "input_tokens": review.usage.input_tokens,
                    "output_tokens": review.usage.output_tokens,
                    "seconds": round(time.perf_counter() - started, 2),
                    "at": datetime.now(UTC).isoformat(),
                }
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                fh.flush()
                count += 1
                if on_result is not None:
                    on_result(row)
    return count


# --- 3. Özet ---------------------------------------------------------------------------------
@dataclass
class VariantScore:
    variant: str
    samples: int
    tp_findings: int
    findings_buggy: int
    hit_lines: int
    expected_lines: int
    detected: int
    buggy: int
    false_alarms: int
    clean: int
    errors: int
    seconds: float
    input_tokens: int

    @property
    def precision(self) -> float:
        return self.tp_findings / self.findings_buggy if self.findings_buggy else 0.0

    @property
    def recall(self) -> float:
        return self.hit_lines / self.expected_lines if self.expected_lines else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0


def _hits(finding: dict[str, Any], expected: list[dict[str, Any]], tol: int) -> set[int]:
    """Bulgunun isabet ettiği beklenen satırların indeksleri."""
    start = finding["line"]
    end = finding.get("end_line") or start
    return {
        i
        for i, e in enumerate(expected)
        if e["path"] == finding["file"] and start - tol <= e["line"] <= end + tol
    }


def score_sample(
    sample: D2Sample, findings: list[dict[str, Any]], tol: int = LINE_TOLERANCE
) -> dict[str, Any]:
    """Tek örnek: isabetli bulgu sayısı, isabet edilen satırlar, tespit / yanlış alarm."""
    if sample.label == "clean":
        return {"false_alarm": bool(findings), "findings": len(findings)}
    covered: set[int] = set()
    tp = 0
    for f in findings:
        hit = _hits(f, sample.expected, tol)
        tp += bool(hit)
        covered |= hit
    return {
        "tp": tp,
        "findings": len(findings),
        "hit_lines": len(covered),
        "expected": len(sample.expected),
        "detected": bool(covered),
    }


def mcnemar(a: Sequence[bool], b: Sequence[bool]) -> tuple[int, int, float]:
    """Eşleştirilmiş ikili sonuçlar için kesin McNemar testi: (yalnız a, yalnız b, p)."""
    only_a = sum(x and not y for x, y in zip(a, b, strict=True))
    only_b = sum(y and not x for x, y in zip(a, b, strict=True))
    n = only_a + only_b
    if n == 0:
        return only_a, only_b, 1.0
    tail = sum(math.comb(n, i) for i in range(min(only_a, only_b) + 1)) / 2**n
    return only_a, only_b, min(1.0, 2 * tail)


def holm(pvalues: Sequence[float]) -> list[float]:
    order = sorted(range(len(pvalues)), key=lambda i: pvalues[i])
    adjusted = [0.0] * len(pvalues)
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (len(pvalues) - rank) * pvalues[i]))
        adjusted[i] = running
    return adjusted


def load_results(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    """(sha, varyant) → son sonuç."""
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                row = json.loads(line)
                rows[(row["sha"], row["variant"])] = row
    return rows


def summarize(
    samples: Sequence[D2Sample],
    results: dict[tuple[str, str], dict[str, Any]],
    *,
    tol: int = LINE_TOLERANCE,
    only: Callable[[D2Sample], bool] | None = None,
) -> tuple[
    list[VariantScore],
    list[tuple[str, int, int, float, float]],
    list[tuple[str, int, int, float, float]],
]:
    """Varyant skorları ve McNemar karşılaştırmaları (hatalı: tespit; temiz: yanlış alarm).

    Yalnızca tüm varyantlarda başarılı sonucu olan örnekler sayılır (eşleştirilmiş tasarım).
    """
    variants = [v for v in VARIANTS if any(k[1] == v for k in results)]
    pool = [s for s in samples if only is None or only(s)]
    complete = [
        s for s in pool if all(results.get((s.sha, v), {}).get("status") == "ok" for v in variants)
    ]
    scores: list[VariantScore] = []
    detected: dict[str, list[bool]] = {}
    alarms: dict[str, list[bool]] = {}
    for v in variants:
        per = [score_sample(s, results[(s.sha, v)]["findings"], tol) for s in complete]
        buggy = [p for s, p in zip(complete, per, strict=True) if s.label == "buggy"]
        clean = [p for s, p in zip(complete, per, strict=True) if s.label == "clean"]
        detected[v] = [p["detected"] for p in buggy]
        alarms[v] = [p["false_alarm"] for p in clean]
        rows = [results[(s.sha, v)] for s in complete]
        scores.append(
            VariantScore(
                variant=v,
                samples=len(complete),
                tp_findings=sum(p["tp"] for p in buggy),
                findings_buggy=sum(p["findings"] for p in buggy),
                hit_lines=sum(p["hit_lines"] for p in buggy),
                expected_lines=sum(p["expected"] for p in buggy),
                detected=sum(detected[v]),
                buggy=len(buggy),
                false_alarms=sum(alarms[v]),
                clean=len(clean),
                errors=sum(results.get((s.sha, v), {}).get("status") == "error" for s in pool),
                seconds=sum(r["seconds"] for r in rows),
                input_tokens=sum(r["input_tokens"] for r in rows),
            )
        )
    pairs = [(a, b) for a, b in (("hybrid", "none"), ("hybrid", "placebo"), ("vector", "none"),
             ("vector", "placebo"), ("placebo", "none"), ("hybrid", "vector"),
             ("structural", "none")) if a in variants and b in variants]  # fmt: skip
    det = [(f"{a} − {b}", *mcnemar(detected[a], detected[b])) for a, b in pairs]
    fa = [(f"{a} − {b}", *mcnemar(alarms[a], alarms[b])) for a, b in pairs]
    det_adj, fa_adj = holm([t[3] for t in det]), holm([t[3] for t in fa])
    return (
        scores,
        [(*t, adj) for t, adj in zip(det, det_adj, strict=True)],
        [(*t, adj) for t, adj in zip(fa, fa_adj, strict=True)],
    )
