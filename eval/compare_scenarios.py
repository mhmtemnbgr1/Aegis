"""Repo içi ve repolar arası (leave-one-project-out) sonuçları karşılaştırır (#17).

`eval/reports/train-<repo>-<yöntem>.json` (within) ve `...-cross.json` (cross) raporları okunur.
İki senaryo da hedef reponun aynı test kümesiyle değerlendirilir.

Kullanım:
    uv run python eval/compare_scenarios.py [eval/reports] [yöntem] > eval/reports/scenarios.md
"""

import json
import sys
from pathlib import Path
from statistics import mean

METRICS = ("roc_auc", "pr_auc", "mcc", "recall_at_20_effort", "popt")
HEADERS = ("ROC-AUC", "PR-AUC", "MCC", "Recall@%20", "Popt")


def main() -> None:
    reports = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("eval/reports")
    method = sys.argv[2] if len(sys.argv) > 2 else "none"
    rows: dict[tuple[str, str, str], dict[str, float]] = {}
    for scenario, suffix in (("within", ""), ("cross", "-cross")):
        for path in sorted(reports.glob(f"train-*-{method}{suffix}.json")):
            data = json.loads(path.read_text("utf-8"))
            if data.get("scenario", "within") != scenario or data["repo"] == "all":
                continue
            for model, result in data["models"].items():
                rows[(data["repo"], model, scenario)] = result["test"]
    repos = sorted({r for r, _, _ in rows})
    models = sorted({m for _, m, _ in rows})

    print(f"## Repo × senaryo (test kümesi, yöntem: {method})\n")
    print("| Repo | Model | Senaryo | " + " | ".join(HEADERS) + " |")
    print("| --- | --- | --- |" + " --- |" * len(HEADERS))
    for repo in repos:
        for model in models:
            for scenario in ("within", "cross"):
                m = rows.get((repo, model, scenario))
                if m is not None:
                    cells = " | ".join(f"{m[k]:.3f}" for k in METRICS)
                    print(f"| {repo} | {model} | {scenario} | {cells} |")

    print("\n## Repolar üzerinden ortalama\n")
    print("| Model | Senaryo | " + " | ".join(HEADERS) + " |")
    print("| --- | --- |" + " --- |" * len(HEADERS))
    for model in models:
        for scenario in ("within", "cross"):
            found = [rows[(r, model, scenario)] for r in repos if (r, model, scenario) in rows]
            if len(found) == len(repos):
                cells = " | ".join(f"{mean(f[k] for f in found):.3f}" for k in METRICS)
                print(f"| {model} | {scenario} | {cells} |")


if __name__ == "__main__":
    main()
