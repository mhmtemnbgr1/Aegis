"""Kalibrasyon yöntemlerini ve bütçe eşiğinin test kümesindeki davranışını özetler (#18).

Girdi: `<dizin>/<repo>-<yöntem>.json` raporları (bkz. plot_calibration.py).

Kullanım:
    uv run python eval/compare_calibration.py eval/reports/calibration > eval/reports/calibration.md
"""

import json
import sys
from pathlib import Path
from statistics import mean

METHODS = ("none", "sigmoid", "isotonic")
BUDGETS = ("0.1", "0.2", "0.3", "0.5")


def main() -> None:
    reports = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("eval/reports/calibration")
    rows: dict[tuple[str, str, str], dict] = {}
    for path in sorted(reports.glob("*.json")):
        method = path.stem.rsplit("-", 1)[-1]
        if method not in METHODS:
            continue
        report = json.loads(path.read_text("utf-8"))
        for model, result in report["models"].items():
            rows[(report["repo"], model, method)] = result
    repos = sorted({r for r, _, _ in rows})
    models = sorted({m for _, m, _ in rows})

    print("## Kalibrasyon (test kümesi, repolar üzerinden ortalama)\n")
    print("| Model | Yöntem | ROC-AUC | PR-AUC | Brier | ECE | Doğrulama ECE |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for model in models:
        for method in METHODS:
            found = [rows[(r, model, method)] for r in repos if (r, model, method) in rows]
            if len(found) != len(repos):
                continue
            t = {
                k: mean(f["test"][k] for f in found) for k in ("roc_auc", "pr_auc", "brier", "ece")
            }
            v = mean(f["valid"]["ece"] for f in found)
            print(
                f"| {model} | {method} | {t['roc_auc']:.3f} | {t['pr_auc']:.3f} | "
                f"{t['brier']:.4f} | {t['ece']:.3f} | {v:.3f} |"
            )

    print("\n## Bütçe eşiği (doğrulamadan seçilir, testte ölçülür; sigmoid)\n")
    print(
        "| Repo | Model | "
        + " | ".join(f"%{float(b) * 100:g} bütçe: pay / recall" for b in BUDGETS)
        + " |"
    )
    print("| --- | --- |" + " --- |" * len(BUDGETS))
    for repo in repos:
        for model in models:
            r = rows.get((repo, model, "sigmoid"))
            if r is None:
                continue
            cells = [
                f"{r['budget'][b]['llm_share']:.0%} / {r['budget'][b]['recall']:.2f}"
                for b in BUDGETS
            ]
            print(f"| {repo} | {model} | " + " | ".join(cells) + " |")
    print("\n| Model | " + " | ".join(f"%{float(b) * 100:g}: pay / recall" for b in BUDGETS) + " |")
    print("| --- |" + " --- |" * len(BUDGETS))
    for model in models:
        found = [rows[(r, model, "sigmoid")] for r in repos if (r, model, "sigmoid") in rows]
        cells = [
            f"{mean(f['budget'][b]['llm_share'] for f in found):.0%} / "
            f"{mean(f['budget'][b]['recall'] for f in found):.2f}"
            for b in BUDGETS
        ]
        print(f"| {model} | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main()
