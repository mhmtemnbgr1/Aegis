"""RQ2 deneyi: hafızasız / plasebo / vektör / hibrit hafızayla LLM incelemesi (#36).

Adımlar:

    # 1. Hazırlık (LLM'siz; madencilik verisi, hafıza indeksi ve klonlar gerekir). Bir kez yapılır,
    #    çıktısı eval/datasets/ altında sürümlenir:
    uv run python eval/rq2.py hazirla

    # 2. Koşu (yalnız eval/datasets/ ve Ollama gerekir). Önce küçük bir kuru koşu:
    uv run python eval/rq2.py kos --model qwen2.5-coder:7b --limit 12
    uv run python eval/rq2.py kos --model qwen2.5-coder:7b          # tamamı; kaldığı yerden sürer

    # 3. Özet tablolar ve testler:
    uv run python eval/rq2.py ozet --model qwen2.5-coder:7b

Sonuçlar `eval/results/rq2/<model>/results.jsonl` dosyasına eklenir (git'e girer); özet aynı
klasörde `summary.md`. Ollama sunucusu başka bir makinedeyse `OLLAMA_HOST` ortam değişkeni.
`--limit`, repolar ve sınıflar arasında sırayla seçilen ilk N örneği koşturur; kuru koşu tam
koşunun bir alt kümesi olduğundan sonuçlar tekrar kullanılır.
"""

import argparse
import sys
import time
from collections import defaultdict
from pathlib import Path

from aegis.config import AegisConfig, AgentConfig
from aegis.experiments.rq2 import (
    DEFAULT_VARIANTS,
    LINE_TOLERANCE,
    VARIANTS,
    load_results,
    prepare_memory,
    read_memory,
    run,
    summarize,
)
from aegis.mining.d2 import D2Sample, read_d2

DATASETS = Path("eval/datasets")
D2, MEMORY, CARDS = DATASETS / "d2.jsonl", DATASETS / "d2-memory.jsonl", DATASETS / "d2-cards.jsonl"
RESULTS = Path("eval/results/rq2")


def interleaved(samples: list[D2Sample]) -> list[D2Sample]:
    """Repo × sınıf grupları arasında sırayla: ilk N örnek her gruptan dengeli gelir."""
    groups: dict[tuple[str, str], list[D2Sample]] = defaultdict(list)
    for s in samples:
        groups[(s.repo, s.label)].append(s)
    queues = [groups[k] for k in sorted(groups)]
    out: list[D2Sample] = []
    for i in range(max(len(q) for q in queues)):
        out += [q[i] for q in queues if i < len(q)]
    return out


def model_dir(model: str) -> Path:
    return RESULTS / model.replace(":", "_").replace("/", "_")


def cmd_prepare(args: argparse.Namespace) -> None:
    config = AegisConfig()
    stats = prepare_memory(
        read_d2(D2),
        Path(config.mining.data_dir),
        Path(config.mining.clone_dir),
        Path(config.memory.index_path),
        MEMORY,
        CARDS,
        config=config,
        seed=args.seed,
    )
    print(f"{MEMORY}, {CARDS}: {stats}")


def cmd_run(args: argparse.Namespace) -> None:
    config = AegisConfig(agents={"analyst": AgentConfig(model=args.model, timeout_seconds=600)})
    samples = interleaved(read_d2(D2))
    if args.repo:
        samples = [s for s in samples if s.repo == args.repo]
    if args.limit:
        samples = samples[: args.limit]
    variants = args.variants.split(",")
    unknown = set(variants) - set(VARIANTS)
    if unknown:
        raise SystemExit(f"bilinmeyen varyant: {', '.join(sorted(unknown))}")
    out = model_dir(args.model) / "results.jsonl"
    total = len(samples) * len(variants)
    started = time.perf_counter()
    seen = [0]

    def progress(row: dict[str, object]) -> None:
        seen[0] += 1
        rate = (time.perf_counter() - started) / seen[0]
        print(
            f"[{seen[0]}] {row['repo']} {str(row['sha'])[:8]} {row['label']:<5} "
            f"{row['variant']:<10} {row['status']:<5} bulgu={len(row['findings'])} "  # type: ignore[arg-type]
            f"{row['seconds']} sn · ~{rate:.0f} sn/koşu",
            file=sys.stderr,
        )

    n = run(samples, read_memory(MEMORY, CARDS), out, config, variants=variants, on_result=progress)
    print(f"{n} yeni koşu ({total} hedef) → {out}")


def _pct(x: float) -> str:
    return f"%{100 * x:.1f}".replace(".", ",")


def cmd_summary(args: argparse.Namespace) -> None:
    samples = read_d2(D2)
    folder = model_dir(args.model)
    results = load_results(folder / "results.jsonl")
    lines = [
        f"# RQ2 sonuçları — {args.model}",
        "",
        f"`eval/rq2.py ozet` ile üretilir. Satır eşleşme toleransı ±{args.tol}. Yalnız tüm "
        "varyantlarda başarılı sonucu olan örnekler sayılır (eşleştirilmiş tasarım).",
        "",
    ]
    subsets = {
        "Tüm örnekler": None,
        "Bilgi kesiminden sonraki commit'ler (#55)": lambda s: s.after_cutoff,
    }
    manual = Path("eval/labels/d2-kontrol.csv")  # elle doğrulanmış alt küme (#69)
    if manual.is_file():
        import csv

        confirmed = {
            r["sha"]
            for r in csv.DictReader(manual.open(encoding="utf-8-sig"))
            if (r["label"], r["answer"]) in (("buggy", "dogru"), ("clean", "temiz"))
        }
        subsets["Elle doğrulanmış alt küme (#69)"] = lambda s: s.sha in confirmed
    for title, only in subsets.items():
        scores, detect, alarm = summarize(samples, results, tol=args.tol, only=only)
        if not scores or not scores[0].samples:
            lines += [f"## {title}", "", "Yeterli sonuç yok.", ""]
            continue
        lines += [
            f"## {title}",
            "",
            "| Varyant | Örnek | Precision | Recall (satır) | F1 | Tespit (hatalı) | "
            "Yanlış alarm (temiz) | Hata | Ort. süre | Ort. girdi token |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for v in scores:
            lines.append(
                f"| {v.variant} | {v.samples} | {_pct(v.precision)} | {_pct(v.recall)} | "
                f"{_pct(v.f1)} | {v.detected}/{v.buggy} | {v.false_alarms}/{v.clean} | "
                f"{v.errors} | {v.seconds / max(v.samples, 1):.1f} sn | "
                f"{v.input_tokens // max(v.samples, 1)} |"
            )
        for name, table in (("Tespit (hatalı commit)", detect), ("Yanlış alarm (temiz)", alarm)):
            lines += [
                "",
                f"**McNemar — {name}:**",
                "",
                "| Karşılaştırma | Yalnız ilki | Yalnız ikincisi | p | p (Holm) |",
                "| --- | --- | --- | --- | --- |",
                *(f"| {c} | {a} | {b} | {p:.3f} | {adj:.3f} |" for c, a, b, p, adj in table),
            ]
        lines.append("")
    (folder / "summary.md").write_text("\n".join(lines) + "\n", "utf-8")
    print("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("hazirla", help="hafıza getirme sonuçlarını hazırla (LLM'siz)")
    p.add_argument("--seed", type=int, default=0)
    p.set_defaults(func=cmd_prepare)
    p = sub.add_parser("kos", help="LLM incelemelerini koştur (Ollama)")
    p.add_argument("--model", default="qwen2.5-coder:7b")
    p.add_argument("--variants", default=",".join(DEFAULT_VARIANTS))
    p.add_argument("--limit", type=int, default=0, help="yalnız ilk N örnek (kuru koşu)")
    p.add_argument("--repo", default="", help="yalnız bu repo (ör. tqdm__tqdm)")
    p.set_defaults(func=cmd_run)
    p = sub.add_parser("ozet", help="tablolar ve McNemar testleri")
    p.add_argument("--model", default="qwen2.5-coder:7b")
    p.add_argument("--tol", type=int, default=LINE_TOLERANCE)
    p.set_defaults(func=cmd_summary)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
