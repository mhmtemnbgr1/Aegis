"""RQ1: ucuz LLM triage'ı ile risk modelinin karşılaştırılması (#67).

Adımlar:

    # 1. Hazırlık (LLM'siz; madencilik verisi ve klonlar gerekir). RQ1 eğrisinin 25 penceresinin
    #    (5 repo × 5) her birinden 50 PR örneklenir; diff'ler ve aynı PR'lardaki LR ve sezgisel
    #    skorlar eval/datasets/rq1-triage.jsonl dosyasına yazılır:
    uv run python eval/rq1_triage.py hazirla

    # 2. Koşu (yalnız eval/datasets/ ve Ollama). Önce kuru koşu, sonra tamamı:
    uv run python eval/rq1_triage.py kos --model qwen2.5-coder:1.5b --limit 25
    uv run python eval/rq1_triage.py kos --model qwen2.5-coder:1.5b

    # 3. Özet:
    uv run python eval/rq1_triage.py ozet --model qwen2.5-coder:1.5b

Sonuçlar `eval/results/rq1-triage/<model>/` altında (git'e girer). "Ucuz" model varsayılan olarak
1.5B'dir; 7B ile de koşturulabilir (`--model qwen2.5-coder:7b`).
"""

import argparse
import math
import sys
import time
from pathlib import Path
from statistics import mean

import numpy as np
import polars as pl

from aegis.experiments.rq1 import (
    MAX_DIFF_CHARS,
    SHARES,
    TriageSample,
    read_samples,
    run,
    window_recalls,
    write_samples,
)

DATA, CLONES = Path(".aegis/data"), Path(".aegis/repos")
SAMPLES = Path("eval/datasets/rq1-triage.jsonl")
RESULTS = Path("eval/results/rq1-triage")
PER_WINDOW = 50


def model_dir(model: str) -> Path:
    return RESULTS / model.replace(":", "_").replace("/", "_")


def cmd_prepare(args: argparse.Namespace) -> None:
    import rq1_curve as rc  # aynı klasördeki betik

    from aegis.config import AegisConfig, TrainingConfig
    from aegis.gatekeeper.split import rolling_windows
    from aegis.mining.gitfiles import git

    d1, prs = pl.read_parquet(DATA / "d1.parquet"), pl.read_parquet(DATA / "d1-pr.parquet")
    samples: list[TriageSample] = []
    for repo in sorted(set(prs["repo"])):
        repo_prs = prs.filter(pl.col("repo") == repo)
        if repo_prs.height < rc.MIN_PRS:
            continue
        files = pl.read_parquet(DATA / repo / "files.parquet")
        paths = {
            sha: [p for p in ps if p]
            for sha, ps in files.group_by("sha")
            .agg(pl.coalesce("new_path", "old_path"))
            .iter_rows()
        }
        commits = d1.filter(pl.col("repo") == repo)
        for w, (start, end) in enumerate(rolling_windows(repo_prs, 5, 0.5)):
            test = repo_prs.filter((pl.col("as_of") >= start) & (pl.col("as_of") < end))
            lr = rc.model_scores("lr+m", commits, start, TrainingConfig(), [test])[0]
            heuristic = rc.heuristic_scores(test, paths, AegisConfig())
            rng = np.random.default_rng([args.seed, w, sum(map(ord, repo))])
            picked = sorted(
                rng.choice(test.height, min(args.per_window, test.height), replace=False)
            )
            for i in picked:
                row = test.row(int(i), named=True)
                diff = git(CLONES / repo, "diff", "--no-color", f"{row['sha']}^1", row["sha"])
                samples.append(
                    TriageSample(
                        repo=repo,
                        window=w,
                        pr=str(row["pr"]),
                        sha=row["sha"],
                        buggy=bool(row["buggy"]),
                        diff=diff[:MAX_DIFF_CHARS],
                        truncated=len(diff) > MAX_DIFF_CHARS,
                        lr=float(lr[i]),
                        heuristic=float(heuristic[i]),
                    )
                )
            print(f"{repo} pencere {w}: {len(picked)}/{test.height} PR", file=sys.stderr)
    write_samples(samples, SAMPLES)
    print(f"{len(samples)} PR ({sum(s.buggy for s in samples)} hatalı) → {SAMPLES}")


def interleaved(samples: list[TriageSample]) -> list[TriageSample]:
    """Pencereler arasında sırayla: kuru koşu her pencereden PR içerir."""
    groups: dict[tuple[str, int], list[TriageSample]] = {}
    for s in samples:
        groups.setdefault((s.repo, s.window), []).append(s)
    queues = [groups[k] for k in sorted(groups)]
    return [q[i] for i in range(max(map(len, queues))) for q in queues if i < len(q)]


def cmd_run(args: argparse.Namespace) -> None:
    from aegis.llm import OllamaProvider

    samples = interleaved(read_samples(SAMPLES))
    if args.limit:
        samples = samples[: args.limit]
    out = model_dir(args.model) / "results.jsonl"
    provider = OllamaProvider(args.model, temperature=0.0, timeout=600)
    started, seen = time.perf_counter(), [0]

    def progress(row: dict[str, object]) -> None:
        seen[0] += 1
        rate = (time.perf_counter() - started) / seen[0]
        print(
            f"[{seen[0]}] {row['pr_key']} risk={row['risk']} {row['seconds']} sn "
            f"· ~{rate:.1f} sn/PR",
            file=sys.stderr,
        )

    n = run(samples, provider, out, on_result=progress)
    print(f"{n} yeni triage ({len(samples)} hedef) → {out}")


def _ci(values: list[float]) -> str:
    x = np.array([v for v in values if not math.isnan(v)])
    rng = np.random.default_rng(2026)
    boots = x[rng.integers(0, len(x), (10_000, len(x)))].mean(axis=1)
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return f"%{100 * x.mean():.1f} [{100 * lo:.1f}; {100 * hi:.1f}]".replace(".", ",")


def cmd_summary(args: argparse.Namespace) -> None:
    import json

    from scipy.stats import wilcoxon

    samples = read_samples(SAMPLES)
    folder = model_dir(args.model)
    rows = [json.loads(x) for x in (folder / "results.jsonl").read_text("utf-8").splitlines() if x]
    latest = {r["pr_key"]: r for r in rows}
    ok = {k: r for k, r in latest.items() if r["risk"] is not None}
    windows = window_recalls(samples, {k: r["risk"] for k, r in ok.items()})
    names = {
        "llm": f"LLM triage ({args.model})",
        "lr": "LR (tam + hafıza)",
        "heuristic": "Sezgisel",
    }
    lines = [
        f"# RQ1 — ucuz LLM triage: {args.model}",
        "",
        f"`eval/rq1_triage.py ozet` ile üretilir. {len(ok)} PR yanıtlandı "
        f"({len(latest) - len(ok)} hata), {len(windows)} pencere. Hücre: yakalanan hatalı PR "
        "oranı, "
        "pencereler üzerinden ortalama [%95 bootstrap GA]; yöntemler aynı PR'ları puanlar.",
        "",
        "| Yöntem | " + " | ".join(f"%{int(100 * s)} LLM" for s in SHARES) + " |",
        "| --- |" + " --- |" * len(SHARES),
    ]
    for m, title in names.items():
        lines.append(
            f"| {title} | " + " | ".join(_ci([w[m][s] for w in windows]) for s in SHARES) + " |"
        )
    lines += [
        "",
        "**Eşleştirilmiş karşılaştırma (Wilcoxon, pencereler):**",
        "",
        "| Pay | LR − LLM (puan) | p | LLM − sezgisel (puan) | p |",
        "| --- | --- | --- | --- | --- |",
    ]
    for s in SHARES:
        cells = []
        for a, b in (("lr", "llm"), ("llm", "heuristic")):
            pairs = [(w[a][s], w[b][s]) for w in windows if not math.isnan(w[a][s])]
            d = [x - y for x, y in pairs]
            p = wilcoxon([x for x, _ in pairs], [y for _, y in pairs]).pvalue if any(d) else 1.0
            cells += [f"{100 * mean(d):+.1f}".replace(".", ","), f"{p:.3f}".replace(".", ",")]
        lines.append(f"| %{int(100 * s)} | " + " | ".join(cells) + " |")
    values = list(ok.values())
    lines += [
        "",
        f"**Triage maliyeti:** PR başına ortalama {mean(r['seconds'] for r in values):.1f} sn, "
        f"{mean(r['input_tokens'] for r in values):.0f} girdi + "
        f"{mean(r['output_tokens'] for r in values):.0f} çıktı token. Risk modeli puanlama "
        "maliyeti ihmal edilebilir (CPU, milisaniyeler).",
    ]
    (folder / "summary.md").write_text("\n".join(lines) + "\n", "utf-8")
    print("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("hazirla", help="PR örneklemi, diff'ler ve LR/sezgisel skorlar (LLM'siz)")
    p.add_argument("--per-window", type=int, default=PER_WINDOW)
    p.add_argument("--seed", type=int, default=0)
    p.set_defaults(func=cmd_prepare)
    p = sub.add_parser("kos", help="LLM triage (Ollama)")
    p.add_argument("--model", default="qwen2.5-coder:1.5b")
    p.add_argument("--limit", type=int, default=0)
    p.set_defaults(func=cmd_run)
    p = sub.add_parser("ozet", help="tablo ve testler")
    p.add_argument("--model", default="qwen2.5-coder:1.5b")
    p.set_defaults(func=cmd_summary)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
