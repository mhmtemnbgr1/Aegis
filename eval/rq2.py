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
klasörde `summary.md`.

İki test seti vardır (`--set`): `revert` (varsayılan; hatalı örnekler tersine çevrilmiş gerçek
düzeltmeler, etiketleri güvenilir) ve `szz` (hatalı örnekler SZZ'nin bug-inducing dediği gerçek
commit'ler; gerçekçi ama etiketleri gürültülü). İki sette temiz örnekler aynıdır: `szz` seti
yalnız hatalı örnekleri koşturur, özette temiz örneklerin sonuçlarını `revert` setinden alır.
Sonuçlar `eval/results/rq2-szz/<model>/` altında.

Bağlam penceresi koddan gelir (`NUM_CTX`, sıcaklık 0); komut satırında ayar verilmez. Her satıra
kullanılan pencere yazılır; pencereyi dolduran (kesilmiş) yanıtlar hata sayılır. Bağlam penceresi
kaydı olmayan eski satırlar (ilk koşu, istemler kesilmişti) yok sayılır, silmek gerekmez.

Ollama sunucusu başka bir makinedeyse `OLLAMA_HOST` ortam değişkeni.
`--limit`, repolar ve sınıflar arasında sırayla seçilen ilk N örneği koşturur; kuru koşu tam
koşunun bir alt kümesi olduğundan sonuçlar tekrar kullanılır.
"""

import argparse
import os
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

NUM_CTX = 16_384
"""RQ2 bağlam penceresi. D2 istemlerinin ~%99'u yanıt payıyla birlikte sığar; sığmayan birkaç
istem için sağlayıcı pencereyi 32k'ya büyütür."""
TIMEOUT_SECONDS = 1_800
DATASETS = Path("eval/datasets")
SETS = {
    "revert": ("d2.jsonl", "d2-memory.jsonl", "d2-cards.jsonl", Path("eval/results/rq2")),
    "szz": (
        "d2-szz.jsonl",
        "d2-szz-memory.jsonl",
        "d2-szz-cards.jsonl",
        Path("eval/results/rq2-szz"),
    ),
}


def paths(name: str) -> tuple[Path, Path, Path, Path]:
    d2, memory, cards, results = SETS[name]
    return DATASETS / d2, DATASETS / memory, DATASETS / cards, results


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


def model_dir(model: str, name: str = "revert") -> Path:
    return paths(name)[3] / model.replace(":", "_").replace("/", "_")


def cmd_prepare(args: argparse.Namespace) -> None:
    config = AegisConfig()
    d2, memory, cards, _ = paths(args.set)
    stats = prepare_memory(
        read_d2(d2),
        Path(config.mining.data_dir),
        Path(config.mining.clone_dir),
        Path(config.memory.index_path),
        memory,
        cards,
        config=config,
        seed=args.seed,
    )
    print(f"{memory}, {cards}: {stats}")


def gpu_note(model: str) -> str | None:
    """Model ekran kartına tam sığmadıysa uyarı metni (Ollama `ps`); sığdıysa ya da bilinmiyorsa
    None."""
    try:
        import ollama

        loaded = ollama.Client(host=os.environ.get("OLLAMA_HOST")).ps().models
    except Exception:
        return None
    for m in loaded:
        if model in (m.model, m.name) and m.size:
            share = (m.size_vram or 0) / m.size
            if share < 0.99:
                return (
                    f"UYARI: model ekran kartına tam sığmadı (%{share * 100:.0f} GPU). Sonuçlar "
                    "geçerli ama koşu yavaş olur. Hızlandırmak için Ollama'yı kapatıp "
                    "OLLAMA_FLASH_ATTENTION=1 ve OLLAMA_KV_CACHE_TYPE=q8_0 ortam değişkenleriyle "
                    "yeniden başlatın (docs/llm-experiments.md)."
                )
    return None


def cmd_run(args: argparse.Namespace) -> None:
    config = AegisConfig(
        agents={
            "analyst": AgentConfig(
                model=args.model,
                temperature=0.0,
                timeout_seconds=TIMEOUT_SECONDS,
                num_ctx=NUM_CTX,
            )
        }
    )
    d2, memory, cards, _ = paths(args.set)
    samples = interleaved(read_d2(d2))
    if args.repo:
        samples = [s for s in samples if s.repo == args.repo]
    if args.limit:
        samples = samples[: args.limit]
    variants = args.variants.split(",")
    unknown = set(variants) - set(VARIANTS)
    if unknown:
        raise SystemExit(f"bilinmeyen varyant: {', '.join(sorted(unknown))}")
    out = model_dir(args.model, args.set) / "results.jsonl"
    total = len(samples) * len(variants)
    started = time.perf_counter()
    seen = [0]

    errors = [0]

    def progress(row: dict[str, object]) -> None:
        seen[0] += 1
        errors[0] += row["status"] == "error"
        if seen[0] == 1 and (note := gpu_note(args.model)):
            print(note, file=sys.stderr)
        rate = (time.perf_counter() - started) / seen[0]
        print(
            f"[{seen[0]}] {row['repo']} {str(row['sha'])[:8]} {row['label']:<5} "
            f"{row['variant']:<10} {row['status']:<5} bulgu={len(row['findings'])} "  # type: ignore[arg-type]
            f"ctx={row['num_ctx']} {row['seconds']} sn · ~{rate:.0f} sn/koşu",
            file=sys.stderr,
        )

    memory_of = read_memory(memory, cards, read_d2(d2))
    try:
        n = run(samples, memory_of, out, config, variants=variants, on_result=progress)
    except RuntimeError as exc:
        raise SystemExit(f"DURDU: {exc}") from exc
    print(f"{n} yeni koşu ({total} hedef), {errors[0]} hata → {out}")
    if errors[0]:
        print(
            "Hata veren koşular aynı komut yeniden çalıştırılınca tekrar denenir. "
            "Bağlam penceresi hataları tekrar ederse sonuçlarla birlikte bildirin.",
            file=sys.stderr,
        )


def _pct(x: float) -> str:
    return f"%{100 * x:.1f}".replace(".", ",")


def cmd_summary(args: argparse.Namespace) -> None:
    d2 = paths(args.set)[0]
    samples = read_d2(d2)
    folder = model_dir(args.model, args.set)
    results = load_results(folder / "results.jsonl")
    if args.set != "revert":
        # Temiz örnekler iki sette aynı: sonuçları ana setten.
        main = read_d2(paths("revert")[0])
        samples += [s for s in main if s.label == "clean"]
        main_results = model_dir(args.model) / "results.jsonl"
        if main_results.is_file():
            results |= {k: v for k, v in load_results(main_results).items() if k[1] == "clean"}
    lines = [
        f"# RQ2 sonuçları ({args.set} seti) — {args.model}",
        "",
        f"`eval/rq2.py ozet` ile üretilir. Satır eşleşme toleransı ±{args.tol}. Yalnız tüm "
        "varyantlarda başarılı sonucu olan örnekler sayılır (eşleştirilmiş tasarım).",
        "",
    ]
    subsets = {
        "Tüm örnekler": None,
        "Bilgi kesiminden sonraki commit'ler (#55)": lambda s: s.after_cutoff,
    }
    manual = Path(
        "eval/labels/d2-kontrol.csv" if args.set == "szz" else "eval/labels/d2-revert-kontrol.csv"
    )
    if manual.is_file():
        import csv

        confirmed = {
            r["sha"]
            for r in csv.DictReader(manual.open(encoding="utf-8-sig"))
            if (r["label"], r["answer"])
            in (("buggy", "dogru"), ("buggy", "kismen"), ("clean", "temiz"))
        }
        matched = confirmed & {s.sha for s in samples}
        matched_buggy = {s.sha for s in samples if s.label == "buggy"} & matched
        matched_clean = {s.sha for s in samples if s.label == "clean"} & matched
        if matched == confirmed and matched_buggy and matched_clean:
            subsets[f"Elle doğrulanmış {args.set} alt kümesi (#69)"] = lambda s, ids=matched: (
                s.sha in ids
            )
        else:
            lines += [
                "## Elle doğrulanmış alt küme",
                "",
                f"`{manual}` içindeki {len(confirmed)} kabul edilmiş SHA'nın "
                f"{len(matched)} tanesi bu {args.set} setinde bulundu; eşleşen hatalı ve temiz "
                "örneklerin ikisi birden tam değil. Alt küme raporlanmadı.",
                "",
            ]
    elif args.set == "revert":
        lines += [
            "## Elle doğrulanmış alt küme",
            "",
            "Bu revert seti için henüz ortak cevaplı bir `d2-revert-kontrol.csv` yok; alt küme "
            "raporlanmadı. Eski `d2-kontrol.csv` etiketleri SZZ setine aittir.",
            "",
        ]
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
    p.add_argument("--set", choices=sorted(SETS), default="revert")
    p.set_defaults(func=cmd_prepare)
    p = sub.add_parser("kos", help="LLM incelemelerini koştur (Ollama)")
    p.add_argument("--model", default="qwen2.5-coder:7b")
    p.add_argument("--set", choices=sorted(SETS), default="revert")
    p.add_argument("--variants", default=",".join(DEFAULT_VARIANTS))
    p.add_argument("--limit", type=int, default=0, help="yalnız ilk N örnek (kuru koşu)")
    p.add_argument("--repo", default="", help="yalnız bu repo (ör. tqdm__tqdm)")
    p.set_defaults(func=cmd_run)
    p = sub.add_parser("ozet", help="tablolar ve McNemar testleri")
    p.add_argument("--model", default="qwen2.5-coder:7b")
    p.add_argument("--set", choices=sorted(SETS), default="revert")
    p.add_argument("--tol", type=int, default=LINE_TOLERANCE)
    p.set_defaults(func=cmd_summary)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
