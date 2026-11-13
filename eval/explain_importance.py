"""Repo ve model başına küresel özellik önemi ve örnek açıklamalar (#19).

Önem = test kümesinde ortalama |katkı| (bkz. aegis.gatekeeper.explain). Modeller
`aegis train` ile `.aegis/models/<repo>/<model>-none.pkl` olarak kaydedilmiş olmalı.

Kullanım:
    uv run python eval/explain_importance.py [.aegis/data] [.aegis/models] > eval/reports/explain.md
"""

import sys
from pathlib import Path

import numpy as np
import polars as pl

from aegis.config import TrainingConfig
from aegis.gatekeeper.explain import contributions
from aegis.gatekeeper.model import FEATURES, MODELS, TrainedModel
from aegis.gatekeeper.split import time_split


def main() -> None:
    data = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".aegis/data")
    models = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".aegis/models")
    d1 = pl.read_parquet(data / "d1.parquet")
    repos = sorted(set(d1["repo"]))
    ranks: dict[str, list[int]] = {f: [] for f in FEATURES}
    examples: list[str] = []

    print("## En önemli 5 özellik (test kümesinde ortalama |katkı|)\n")
    print("| Repo | Model | 1 | 2 | 3 | 4 | 5 |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for repo in repos:
        split = time_split(d1.filter(pl.col("repo") == repo), TrainingConfig())
        for name in MODELS:
            path = models / repo / f"{name}-none.pkl"
            if not path.is_file():
                continue
            model = TrainedModel.load(path)
            phi, _ = contributions(model, split.test)
            importance = np.abs(phi).mean(axis=0)
            order = np.argsort(-importance)
            for rank, i in enumerate(order):
                ranks[FEATURES[i]].append(rank + 1)
            share = importance / importance.sum()
            cells = [f"{FEATURES[i]} ({share[i]:.0%})" for i in order[:5]]
            print(f"| {repo} | {name} | " + " | ".join(cells) + " |")
            if name == "lr":
                prob = model.predict_proba(split.test)
                top = int(np.argmax(prob))
                row = split.test[top]
                lines = "; ".join(e.text for e in model.explain_pr(row))
                buggy = "hatalı" if row["buggy"][0] else "temiz"
                examples.append(
                    f"- **{repo}** `{row['sha'][0][:10]}` (skor {prob[top]:.2f}, {buggy}): {lines}"
                )

    print("\n## Ortalama sıra (tüm repo ve modeller; küçük = önemli)\n")
    print("| Özellik | Ortalama sıra | İlk 3'te |")
    print("| --- | --- | --- |")
    for feature, r in sorted(ranks.items(), key=lambda kv: np.mean(kv[1]) if kv[1] else 99):
        if r:
            print(f"| {feature} | {np.mean(r):.1f} | {sum(x <= 3 for x in r)}/{len(r)} |")

    print("\n## Örnek PR açıklamaları (LR, test kümesindeki en riskli commit; riski artıranlar)\n")
    print("\n".join(examples))


if __name__ == "__main__":
    main()
