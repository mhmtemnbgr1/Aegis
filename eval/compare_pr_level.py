"""PR düzeyinde model ile commit modelinin PR'a birleştirilmesini karşılaştırır (#73).

Her repo için PR satırları (`d1-pr.parquet`) zaman sırasıyla bölünür. Aynı PR test kümesi iki
yolla puanlanır:

1. **PR modeli:** PR satırlarıyla (birleşik diff + n_commits, n_authors) eğitilen model.
2. **Commit modeli → PR:** Commit satırlarıyla, yalnızca PR test döneminden (tampon dahil) önceki
   commit'lerle eğitilen model; PR skoru `1 − Π(1 − pᵢ)` (review akışının şu anki yöntemi).

Sonuçlar merge ve squash stili repolar için ayrı raporlanır.

Kullanım:
    uv run python eval/compare_pr_level.py [.aegis/data] [model] > eval/reports/pr-level.md
"""

import sys
from datetime import timedelta
from pathlib import Path
from statistics import mean

import numpy as np
import polars as pl

from aegis.config import TrainingConfig
from aegis.gatekeeper.calibration import pr_score
from aegis.gatekeeper.metrics import evaluate
from aegis.gatekeeper.model import FEATURES, train_model
from aegis.gatekeeper.split import Split, labels_as_of, time_split
from aegis.mining.prs import PR_FEATURES

METRICS = ("roc_auc", "pr_auc", "recall_at_20_effort", "popt")
HEADERS = ("ROC-AUC", "PR-AUC", "Recall@%20", "Popt")


def commit_split(commits: pl.DataFrame, test: pl.DataFrame, cfg: TrainingConfig) -> Split:
    """PR test döneminden önceki commit'lerle eğitim/doğrulama; test = PR test commit'leri."""
    delay = timedelta(days=cfg.label_delay_days)
    test_start = test["as_of"].min()
    pool = commits.filter(pl.col("as_of") < test_start - delay).sort("as_of")
    share = cfg.valid_fraction / (1 - cfg.test_fraction)
    valid_start = pool["as_of"][pool.height - max(1, round(pool.height * share))]
    members = set(test["commits"].explode().drop_nulls())
    return Split(
        train=labels_as_of(pool.filter(pl.col("as_of") < valid_start - delay), valid_start),
        valid=labels_as_of(pool.filter(pl.col("as_of") >= valid_start), test_start),
        test=commits.filter(pl.col("sha").is_in(members)),
        valid_start=valid_start,
        test_start=test_start,
    )


def main() -> None:
    data = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".aegis/data")
    name = sys.argv[2] if len(sys.argv) > 2 else "lr"
    cfg = TrainingConfig()
    d1 = pl.read_parquet(data / "d1.parquet")
    prs = pl.read_parquet(data / "d1-pr.parquet")
    rows: list[tuple[str, str, int, int, dict[str, float], dict[str, float]]] = []
    for repo in sorted(set(prs["repo"])):
        repo_prs = prs.filter(pl.col("repo") == repo)
        style = "merge" if (repo_prs["style"] == "merge").mean() > 0.5 else "squash"  # type: ignore[operator]
        split = time_split(repo_prs, cfg)
        y = split.test["buggy"].to_numpy()
        effort = (split.test["la"] + split.test["ld"]).clip(lower_bound=1).to_numpy()
        pr_model = train_model(split, name, features=PR_FEATURES)  # type: ignore[arg-type]
        pr_metrics = evaluate(y, pr_model.predict_proba(split.test), effort)

        commits = d1.filter(pl.col("repo") == repo)
        c_model = train_model(commit_split(commits, split.test, cfg), name, features=FEATURES)  # type: ignore[arg-type]
        prob = dict(zip(commits["sha"], c_model.predict_proba(commits), strict=True))
        agg = np.array([pr_score([prob[s] for s in members]) for members in split.test["commits"]])
        agg_metrics = evaluate(y, agg, effort)
        rows.append((repo, style, split.test.height, int(y.sum()), pr_metrics, agg_metrics))

    print(f"## PR modeli ve commit modeli → PR (test kümesi, model: {name})\n")
    print("| Repo | Stil | Test PR (hatalı) | Yöntem | " + " | ".join(HEADERS) + " |")
    print("| --- | --- | --- | --- |" + " --- |" * len(HEADERS))
    for repo, style, n, pos, pr_m, agg_m in rows:
        for label, m in (("PR modeli", pr_m), ("commit → PR", agg_m)):
            cells = " | ".join(f"{m[k]:.3f}" for k in METRICS)
            print(f"| {repo} | {style} | {n} ({pos}) | {label} | {cells} |")

    print("\n## Stile göre ortalama (en az 20 hatalı PR'ı olan repolar)\n")
    print("| Stil | Repolar | Yöntem | " + " | ".join(HEADERS) + " |")
    print("| --- | --- | --- |" + " --- |" * len(HEADERS))
    for style in ("merge", "squash"):
        group = [r for r in rows if r[1] == style and r[3] >= 20]
        if not group:
            continue
        names = ", ".join(r[0].split("__")[-1] for r in group)
        for label, idx in (("PR modeli", 4), ("commit → PR", 5)):
            cells = " | ".join(f"{mean(r[idx][k] for r in group):.3f}" for k in METRICS)  # type: ignore[index]
            print(f"| {style} | {names} | {label} | {cells} |")


if __name__ == "__main__":
    main()
