"""Sınıf dengesizliği yöntemlerini `aegis train` raporlarından karşılaştırır (#16).

Her repo, model ve yöntem için `eval/reports/train-<repo>-<yöntem>.json` okunur. Yöntem
doğrulama kümesindeki ortalama PR-AUC'ye göre seçilir; test metrikleri yalnızca raporlanır.

Kullanım:
    uv run python eval/compare_imbalance.py [eval/reports] > eval/reports/imbalance.md
"""

import json
import sys
from pathlib import Path
from statistics import mean

METHODS = ("none", "weights", "undersample", "smote")
METRICS = ("roc_auc", "pr_auc", "mcc", "recall_at_20_effort", "popt")
HEADERS = ("ROC-AUC", "PR-AUC", "MCC", "Recall@%20", "Popt")


def load(reports: Path) -> dict[tuple[str, str, str], dict[str, dict[str, float]]]:
    out: dict[tuple[str, str, str], dict[str, dict[str, float]]] = {}
    for path in sorted(reports.glob("train-*.json")):
        data = json.loads(path.read_text("utf-8"))
        if data.get("level", "commit") != "commit":
            continue
        if data.get("scenario", "within") != "within" or data["repo"] == "all":
            continue
        for model, result in data["models"].items():
            key = (data["repo"], model, data["imbalance"])
            out[key] = {"valid": result["valid"], "test": result["test"]}
    return out


def main() -> None:
    reports = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("eval/reports")
    rows = load(reports)
    repos = sorted({r for r, _, _ in rows})
    models = sorted({m for _, m, _ in rows})

    print("## Repolar üzerinden ortalama\n")
    print("| Model | Yöntem | Doğrulama PR-AUC | Test " + " | Test ".join(HEADERS) + " |")
    print("| --- | --- | --- |" + " --- |" * len(HEADERS))
    best: dict[str, tuple[float, str]] = {}
    for model in models:
        for method in METHODS:
            found = [rows[(r, model, method)] for r in repos if (r, model, method) in rows]
            if len(found) != len(repos):
                continue
            valid = mean(f["valid"]["pr_auc"] for f in found)
            test = [mean(f["test"][k] for f in found) for k in METRICS]
            best[model] = max(best.get(model, (-1.0, "")), (valid, method))
            cells = " | ".join(f"{v:.3f}" for v in test)
            print(f"| {model} | {method} | {valid:.3f} | {cells} |")
    print("\nDoğrulamaya göre seçilen: " + ", ".join(f"{m}: {b[1]}" for m, b in best.items()))

    print("\n## Repo bazında test PR-AUC\n")
    print("| Repo | Model | " + " | ".join(METHODS) + " |")
    print("| --- | --- |" + " --- |" * len(METHODS))
    for repo in repos:
        for model in models:
            found = [rows.get((repo, model, m)) for m in METHODS]
            cells = [f"{f['test']['pr_auc']:.3f}" if f else "–" for f in found]
            print(f"| {repo} | {model} | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main()
