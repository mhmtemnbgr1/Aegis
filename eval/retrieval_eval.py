"""Hafıza getirme değerlendirmesi: Recall@1/3/5 ve MRR (#27, RQ2'nin LLM'siz kısmı).

**Sorgular:** SZZ'ye göre hata getiren commit'ler (X). Sorgu yalnızca X'ten kurulur
(`query_from_range(X~1, X)`: dosyalar, değişen fonksiyonlar, kod, diff) ve yalnızca X'ten önce
düzeltilmiş kartlar aranır (zamansal filtre).

**İlgili kartlar:** X'in getirdiği hata sonradan bir fix F ile düzeltildi (SZZ). X'ten önce tarihli
ve F'nin düzelttiği fonksiyonlardan en az birini düzeltmiş kartlar ilgilidir: "hafıza, bu PR'ın
hatasının gerçekte düzeltileceği koddaki geçmiş fix'leri getiriyor mu?". F geleceğe aittir; yalnızca
puanlamada kullanılır. İlgili kartı olmayan sorgular atlanır.

**Ölçütler:** Recall@k = ilk k sonuçta en az bir ilgili kart olan sorguların payı; MRR = ilk ilgili
kartın sırasının tersi (ilk 10'da yoksa 0). Modlar: yapısal, BM25, vektör, hibrit ve rastgele
(aynı zamansal filtreyle). Hibrit ile diğerleri, sorgu başına ters sıra üzerinde eşleştirilmiş
Wilcoxon testiyle karşılaştırılır.

Sınırlamalar: ilgi tanımı fonksiyon adına dayandığı için yapısal aramayı kayırır; SZZ eşlemelerinin
~%31'i doğru olduğundan (docs/mining-schema.md) bazı sorguların "doğru cevabı" yanlıştır.

Kullanım:
    uv run python eval/retrieval_eval.py [sorgu/repo, ör. 150] > eval/reports/retrieval.md
"""

import random
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

import polars as pl
from scipy.stats import wilcoxon

from aegis.memory.retrieve import Retriever, query_from_range

DATA, REPOS, INDEX = Path(".aegis/data"), Path(".aegis/repos"), Path(".aegis/memory")
MODES = ("structural", "bm25", "vector", "hybrid", "random")
KS = (1, 3, 5)
DEPTH = 10
SEED = 7


def queries(slug: str, retriever: Retriever, limit: int) -> list[dict[str, Any]]:
    """(X, ilgili kart kimlikleri) çiftleri; X başına tek sorgu, ilgilisi olmayanlar atlanır."""
    szz = pl.read_parquet(DATA / slug / "szz.parquet")
    commits = pl.read_parquet(DATA / slug / "commits.parquet").select("sha", "committer_date")
    when = dict(commits.iter_rows())
    fixed_funcs: dict[str, set[str]] = {}
    for card in retriever.cards:
        fixed_funcs[card.fix_sha] = set(card.functions)
    by_inducing: dict[str, set[str]] = defaultdict(set)
    for fix, inducing in szz.select("fix_sha", "inducing_sha").unique().iter_rows():
        by_inducing[inducing] |= fixed_funcs.get(fix, set())
    out = []
    for inducing, funcs in by_inducing.items():
        if not funcs or inducing not in when:
            continue
        t = when[inducing]
        relevant = {
            c.id
            for c in retriever.cards
            if c.fix_date.timestamp() < t.timestamp() and funcs & set(c.functions)
        }
        if relevant:
            out.append({"sha": inducing, "when": t, "relevant": relevant})
    random.Random(SEED).shuffle(out)
    return out[:limit]


def evaluate(slug: str, limit: int) -> list[dict[str, Any]]:
    retriever = Retriever.load(DATA / slug / "cards.jsonl", INDEX / slug)
    rng = random.Random(SEED)
    rows = []
    for q in queries(slug, retriever, limit):
        try:
            query = query_from_range(REPOS / slug, f"{q['sha']}~1", q["sha"], before=q["when"])
        except Exception:  # kök commit ya da okunamayan aralık
            continue
        record: dict[str, Any] = {"repo": slug, "sha": q["sha"], "n_relevant": len(q["relevant"])}
        for mode in MODES:
            if mode == "random":
                pool = [c.id for c in retriever.cards if c.fix_date < q["when"]]
                ids = rng.sample(pool, min(DEPTH, len(pool)))
            else:
                ids = [h.card_id for h in retriever.search(query, k=DEPTH, mode=mode)]  # type: ignore[arg-type]
            first = next((r for r, i in enumerate(ids, 1) if i in q["relevant"]), None)
            record[mode] = 1.0 / first if first else 0.0
            for k in KS:
                record[f"{mode}@{k}"] = float(first is not None and first <= k)
        rows.append(record)
    print(f"{slug}: {len(rows)} sorgu", file=sys.stderr)
    return rows


def table(rows: list[dict[str, Any]], title: str) -> list[str]:
    out = [f"### {title} ({len(rows)} sorgu)", ""]
    out.append("| Mod | Recall@1 | Recall@3 | Recall@5 | MRR |")
    out.append("| --- | --- | --- | --- | --- |")
    for mode in MODES:
        cells = [f"{mean(r[f'{mode}@{k}'] for r in rows):.3f}" for k in KS]
        out.append(f"| {mode} | " + " | ".join(cells) + f" | {mean(r[mode] for r in rows):.3f} |")
    return out


def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 150
    slugs = sorted(p.parent.name for p in DATA.glob("*/cards.jsonl"))
    rows = [r for slug in slugs for r in evaluate(slug, limit)]
    lines = ["# Hafıza getirme değerlendirmesi (#27)", "", *table(rows, "Tüm repolar"), ""]
    lines += ["### Hibrit ile diğer modlar (sorgu başına ters sıra, Wilcoxon)", ""]
    lines += ["| Karşılaştırma | Ortalama fark (MRR) | p |", "| --- | --- | --- |"]
    for other in ("structural", "bm25", "vector", "random"):
        a, b = [r["hybrid"] for r in rows], [r[other] for r in rows]
        diff = [x - y for x, y in zip(a, b, strict=True)]
        p = wilcoxon(a, b).pvalue if any(diff) else 1.0
        lines.append(f"| hybrid − {other} | {mean(diff):+.3f} | {p:.3g} |")
    lines.append("")
    for slug in slugs:
        part = [r for r in rows if r["repo"] == slug]
        if part:
            lines += table(part, slug) + [""]
    print("\n".join(lines))
    # Sorgu başına sonuçlar: güven aralıkları ve sonuç belgesi için (eval/results.py).
    import json

    Path("eval/reports/retrieval.json").write_text(json.dumps(rows, indent=0), "utf-8")


if __name__ == "__main__":
    main()
