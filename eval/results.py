"""Sonuç belgesi: tüm LLM'siz sonuçları tek yerde toplar (#53) → `docs/results.md`.

Girdiler (önce üretilmiş olmalı):
- `.aegis/data/d1.json`, `d1.parquet`, `d1-pr.parquet` (veri),
- `eval/labels/szz-kontrol.csv`, `fix-kontrol.csv` (etiket kalitesi),
- `eval/reports/train-<repo>-none.json` ve `...-none-cross.json` (`aegis train`, repo içi / repolar arası),
- `eval/reports/rq1/curves.json` (`eval/rq1_curve.py`),
- `eval/reports/retrieval.json` (`eval/retrieval_eval.py`).

İstatistik: güven aralıkları birimler (repo × pencere ya da sorgu) üzerinden 10.000 tekrarlı
yüzdelik bootstrap ile; eşleştirilmiş karşılaştırmalar Wilcoxon işaretli sıra testi, etki büyüklüğü
eşleştirilmiş rank-biserial korelasyon (r), çoklu karşılaştırmalar her tabloda Holm düzeltmesi.

Kullanım:
    uv run python eval/results.py
"""

import csv
import json
import math
import subprocess
import sys
from collections import Counter
from pathlib import Path
from statistics import mean, median

import numpy as np
import polars as pl
from scipy.stats import rankdata, wilcoxon

DATA, REPORTS, LABELS = Path(".aegis/data"), Path("eval/reports"), Path("eval/labels")
OUT = Path("docs/results.md")
RNG = np.random.default_rng(2026)
BOOT = 10_000


def ci(values: list[float]) -> tuple[float, float, float]:
    """(ortalama, %2,5, %97,5) yüzdelik bootstrap."""
    x = np.asarray([v for v in values if not math.isnan(v)], dtype=float)
    idx = RNG.integers(0, len(x), (BOOT, len(x)))
    means = x[idx].mean(axis=1)
    return float(x.mean()), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def fmt_ci(values: list[float], pct: bool = True) -> str:
    m, lo, hi = ci(values)
    if pct:
        text = f"%{100 * m:.1f} [{100 * lo:.1f}; {100 * hi:.1f}]"
    else:
        text = f"{m:.3f} [{lo:.3f}; {hi:.3f}]"
    return text.replace(".", ",")


def paired(a: list[float], b: list[float]) -> tuple[float, float, float]:
    """(ortalama fark, Wilcoxon p, rank-biserial r)."""
    pairs = [(x, y) for x, y in zip(a, b, strict=True) if not (math.isnan(x) or math.isnan(y))]
    d = np.array([x - y for x, y in pairs])
    nz = d[d != 0]
    if len(nz) == 0:
        return 0.0, 1.0, 0.0
    p = float(wilcoxon([x for x, _ in pairs], [y for _, y in pairs]).pvalue)
    ranks = rankdata(np.abs(nz))
    r = float((ranks[nz > 0].sum() - ranks[nz < 0].sum()) / ranks.sum())
    return float(d.mean()), p, r


def holm(ps: list[float]) -> list[float]:
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    out = [0.0] * len(ps)
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (len(ps) - rank) * ps[i]))
        out[i] = running
    return out


def repo_name(slug: str) -> str:
    """`psf__black` → black; `httpie__cli` → httpie."""
    owner, name = slug.split("__", 1)
    return owner if name == "cli" else name


def p_text(p: float) -> str:
    return "< 0,001" if p < 0.001 else f"{p:.3f}".replace(".", ",")


def num(x: float, digits: int = 3) -> str:
    return f"{x:.{digits}f}".replace(".", ",")


def comparison_table(rows: list[tuple[str, list[float], list[float]]], pct: bool) -> list[str]:
    stats = [paired(a, b) for _, a, b in rows]
    adjusted = holm([s[1] for s in stats])
    unit = "puan" if pct else "MRR"
    out = [
        f"| Karşılaştırma | Ortalama fark ({unit}) | Wilcoxon p (Holm) | Etki (r) |",
        "| --- | --- | --- | --- |",
    ]
    for (name, _, _), (d, _, r), p in zip(rows, stats, adjusted, strict=True):
        diff = f"{100 * d:+.1f}" if pct else f"{d:+.3f}"
        out.append(f"| {name} | {diff.replace('.', ',')} | {p_text(p)} | {num(r, 2)} |")
    return out


def included_repos() -> set[str]:
    """D1'e alınan repolar (manifestte `included`); eşik altı repoların eski raporları sayılmaz."""
    repos = json.loads((DATA / "d1.json").read_text("utf-8"))["repos"]
    return {r["repo"] for r in repos if r.get("included", True)}


# --- Bölümler --------------------------------------------------------------------------------
def section_data() -> list[str]:
    manifest = json.loads((DATA / "d1.json").read_text("utf-8"))
    stats = [s for s in manifest["repos"] if s.get("included", True)]
    left_out = [s for s in manifest["repos"] if not s.get("included", True)]
    prs = pl.read_parquet(DATA / "d1-pr.parquet")
    pr_stats = {
        r: (h, int(b), m)
        for r, h, b, m in prs.group_by("repo")
        .agg(pl.len(), pl.col("buggy").sum(), (pl.col("style") == "merge").mean())
        .iter_rows()
    }
    out = [
        "## 1. Veri",
        "",
        "| Repo | Commit | Fix | Hatalı commit | Oran | PR | Hatalı PR | PR stili |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for s in sorted(stats, key=lambda s: -s["positives"]):
        n, b, merge = pr_stats.get(s["repo"], (0, 0, 0.0))
        style = "merge" if merge > 0.5 else "squash"
        counts = [
            f"{v:,}".replace(",", ".") for v in (s["commits"], s["fixes"], s["positives"], n, b)
        ]
        rate = f"%{100 * s['positive_rate']:.1f}".replace(".", ",")
        out.append(
            f"| {repo_name(s['repo'])} | {counts[0]} | {counts[1]} | {counts[2]} | {rate} | "
            f"{counts[3]} | {counts[4]} | {style} |"
        )
    total = sum(s["commits"] for s in stats)
    out += [
        "",
        f"Toplam {total:,} commit, {prs.height:,} PR. Pencere: tüm geçmiş (#13).".replace(",", "."),
    ]
    if left_out:
        names = ", ".join(f"{repo_name(s['repo'])} ({s['positives']})" for s in left_out)
        out += [
            "",
            f"{manifest['min_positives']} hatalı commit eşiğinin altında kaldığı için D1'e alınmayan "
            f"repolar: {names}. Seçim ve gerekçe: `docs/target-repos.md`.",
        ]
    return out


def _labels(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _kappa(a: list[str], b: list[str]) -> float:
    n = len(a)
    po = sum(x == y for x, y in zip(a, b, strict=True)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[c] / n * cb[c] / n for c in ("evet", "hayir", "belirsiz"))
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def section_labels() -> list[str]:
    out = [
        "## 2. Etiket kalitesi (#8, #9)",
        "",
        "Son etiketler iki bağımsız öneri seti görülerek bir ekip üyesince verildi (yöntem ve "
        "sınırlamalar: `docs/mining-schema.md`, Etiket kalitesi).",
        "",
        "| Set | Karar – öneri 1 κ | Karar – öneri 2 κ | Öneri 1 – öneri 2 κ |",
        "| --- | --- | --- | --- |",
    ]
    for name, file in (
        ("SZZ eşlemeleri (50)", "szz-kontrol.csv"),
        ("Fix commit'leri (200)", "fix-kontrol.csv"),
    ):
        rows = _labels(LABELS / file)
        h = [r["correct"] for r in rows]
        o = [r["suggested_oneri1"] for r in rows]
        s = [r["suggested_oneri2"] for r in rows]
        out.append(
            f"| {name} | {num(_kappa(h, o), 2)} | {num(_kappa(h, s), 2)} | {num(_kappa(o, s), 2)} |"
        )
    szz = [r["correct"] for r in _labels(LABELS / "szz-kontrol.csv") if r["correct"] != "belirsiz"]
    correct = [1.0 if c == "evet" else 0.0 for c in szz]
    out += [
        "",
        f"- **SZZ eşleme doğruluğu:** {int(sum(correct))}/{len(correct)} = {fmt_ci(correct)} (%95 GA).",
    ]
    tune = subprocess.run(
        [sys.executable, "eval/tune_fix.py", str(LABELS / "fix-kontrol.csv")],
        capture_output=True, text=True, encoding="utf-8", check=True,
    ).stdout.strip().splitlines()  # fmt: skip
    out += [
        "- **Fix sınıflandırıcısı** (`eval/tune_fix.py`; aynı 200 commit'te ayarlandı, iyimser):",
        "",
    ]
    out += tune
    return out


def section_models() -> list[str]:
    out = [
        "## 3. RQ1 — Risk modeli (commit düzeyi, tek zaman bölmesi)",
        "",
        "Varsayılan özellik seti (Kamei + riskli yol + test oranı + hafıza), sigmoid kalibrasyon, "
        "zaman sıralı bölme. Repolar arası: model yalnızca diğer 5 repoyla eğitilir, aynı test kümesi.",
        "",
        "| Model | Senaryo | ROC-AUC | PR-AUC | Recall@%20 efor | Brier | ECE |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for scenario, suffix in (("repo içi", ""), ("repolar arası", "-cross")):
        files = sorted(
            p for p in REPORTS.glob(f"train-*-none{suffix}.json") if "train-pr-" not in p.name
        )
        reports = [json.loads(p.read_text("utf-8")) for p in files]
        reports = [
            r
            for r in reports
            if r["repo"] in included_repos()
            and r.get("scenario", "within") == ("cross" if suffix else "within")
        ]
        for model in ("lr", "rf", "lightgbm"):
            ms = [r["models"][model]["test"] for r in reports if model in r["models"]]
            if not ms:
                continue
            cells = [
                num(mean(m[k] for m in ms))
                for k in ("roc_auc", "pr_auc", "recall_at_20_effort", "brier", "ece")
            ]
            out.append(f"| {model} | {scenario} | " + " | ".join(cells) + " |")
    out += [
        "",
        f"Ortalama {len(reports)} repo üzerinden. Repolar arası genel model repo içi modelden geri "
        "kalmıyor; hafıza sayımları (geçmiş hata kartı) repolar arasında iyi genelleşiyor.",
    ]
    return out


def section_rq1() -> list[str]:
    records = json.loads((REPORTS / "rq1" / "curves.json").read_text("utf-8"))
    shares = [round(0.05 * i, 2) for i in range(21)]
    methods = [
        m
        for m in ("lr+m", "rf+m", "lr+", "rf+", "lr", "lr+mp", "rf+mp", "heuristic")
        if m in records[0]
    ]
    labels = {
        "lr+m": "LR (tam + hafıza)", "rf+m": "RF (tam + hafıza)", "lr+": "LR (tam)", "rf+": "RF (tam)",
        "lr": "LR (Kamei)", "lr+mp": "LR (hafıza plasebosu)", "rf+mp": "RF (hafıza plasebosu)",
        "heuristic": "Sezgisel kural",
    }  # fmt: skip
    n_windows = len(records)
    out = [
        "## 4. RQ1 — Maliyet–recall eğrisi (PR düzeyi, kayan pencere)",
        "",
        f"{n_windows} birim (5 repo × 5 zaman penceresi; tqdm 61 PR ile dışarıda). Her pencerede modeller "
        "yalnızca pencereden önceki commit'lerle eğitildi; RF 5 tohum ortalaması. Hücre: yakalanan hatalı PR "
        "oranı, ortalama [%95 bootstrap GA].",
        "",
        "![Maliyet–recall eğrisi](figures/rq1-curve.svg)",
        "",
        "| Yöntem | %10 LLM | %20 LLM | %40 LLM | %60 LLM |",
        "| --- | --- | --- | --- | --- |",
    ]
    for m in methods:
        cells = [
            fmt_ci([r[m]["curve"][shares.index(s)] for r in records]) for s in (0.1, 0.2, 0.4, 0.6)
        ]
        out.append(f"| {labels[m]} | " + " | ".join(cells) + " |")
    out.append("| Rastgele | %10 | %20 | %40 | %60 |")
    out += ["", "**İşletme noktaları** (eşik önceki pencereden, ölçüm mevcut pencerede):", ""]
    out += ["| Nokta | Yöntem | Eleme (LLM'e gitmeyen) | Recall |", "| --- | --- | --- | --- |"]
    for point, title in (
        ("cost", "maliyet odaklı (hedef %60 eleme)"),
        ("safety", "güvenlik odaklı (hedef ≥ %90 recall)"),
    ):
        for m in ("lr+m", "heuristic"):
            if m not in records[0]:
                continue
            elim = [1 - r[m][point][1] for r in records]
            rec = [r[m][point][2] for r in records]
            out.append(f"| {title} | {labels[m]} | {fmt_ci(elim)} | {fmt_ci(rec)} |")
    out += [
        "",
        "**Güvenlik eşiği alternatifleri** (aynı 25 pencere; ortalama [%95 bootstrap GA]):",
        "",
        "Eşikler yalnızca geçmiş pencerelerden seçilir. 90 günlük seçenek, PR tarihinden en az "
        "90 gün önceki PR'ları kullanır ve etiketleri bu kesim tarihindeki bilgiyle belirler.",
        "",
        "| Kural | Yöntem | Eleme (LLM'e gitmeyen) | Gerçekleşen recall |",
        "| --- | --- | --- | --- |",
    ]
    safety_options = {
        "safety-k2": "Son 2 pencere, hedef recall %90",
        "safety-k3": "Son 3 pencere, hedef recall %90",
        "safety-95": "Son pencere, hedef recall %95",
        "safety-known": "90 gün olgunlaşmış etiketler, hedef recall %90",
    }
    for point, title in safety_options.items():
        for m in ("lr+m", "heuristic"):
            elimination = [1 - r[m][point][1] for r in records]
            recall = [r[m][point][2] for r in records]
            out.append(f"| {title} | {labels[m]} | {fmt_ci(elimination)} | {fmt_ci(recall)} |")
    eligible = []
    for point, title in safety_options.items():
        for m in ("lr+m", "heuristic"):
            elimination = [1 - r[m][point][1] for r in records]
            recall = [r[m][point][2] for r in records]
            known = [value for value in recall if not math.isnan(value)]
            if known and mean(known) >= 0.90:
                eligible.append((mean(elimination), title, m, elimination, recall))
    if eligible:
        _, title, method, elimination, recall = max(eligible, key=lambda row: row[0])
        out.append(
            f"| **Seçilen: {title}** | **{labels[method]}** | "
            f"**{fmt_ci(elimination)}** | **{fmt_ci(recall)}** |"
        )
    else:
        out.append("| Seçilen | – | – | Hiçbir seçenek ortalama %90'a ulaşmadı |")
    out += [
        "",
        "Ürün çalışma anında aynı recall temelli eşik isteğe bağlıdır: `[gatekeeper] "
        'threshold_policy = "safety"` ve `safety_recall_target = 0.90`. Eşik, 90 günlük '
        "etiket tamponunu geçmiş model doğrulama örneklerinden seçilir. Varsayılan `budget` "
        "politikası değişmez.",
    ]
    for share in (0.1, 0.2, 0.4):
        i = shares.index(share)
        pairs = [
            ("LR (tam + hafıza) − sezgisel", "lr+m", "heuristic"),
            ("RF (tam + hafıza) − sezgisel", "rf+m", "heuristic"),
            ("LR: hafıza − tam", "lr+m", "lr+"),
            ("RF: hafıza − tam", "rf+m", "rf+"),
            ("LR: hafıza − plasebo", "lr+m", "lr+mp"),
            ("RF: hafıza − plasebo", "rf+m", "rf+mp"),
            ("LR: plasebo − tam", "lr+mp", "lr+"),
        ]
        rows = [
            (name, [r[a]["curve"][i] for r in records], [r[b]["curve"][i] for r in records])
            for name, a, b in pairs
            if a in records[0] and b in records[0]
        ]
        out += ["", f"**Eşleştirilmiş karşılaştırmalar, %{100 * share:.0f} LLM payında:**", ""]
        out += comparison_table(rows, pct=True)
    return out


def section_rq2() -> list[str]:
    rows = json.loads((REPORTS / "retrieval.json").read_text("utf-8"))
    modes = ("hybrid", "vector", "bm25", "structural", "random")
    names = {
        "hybrid": "Hibrit (RRF)",
        "vector": "Vektör (LSA)",
        "bm25": "BM25",
        "structural": "Yapısal",
        "random": "Rastgele",
    }
    out = [
        "## 5. RQ2 (LLM'siz) — Hafıza getirme",
        "",
        f"{len(rows)} sorgu (6 repo; sorgu = SZZ'ye göre hata getiren commit, ilgili = bu hatayı sonradan "
        "düzelten fix'in fonksiyonlarını daha önce düzeltmiş kartlar; yalnızca sorgu tarihinden önceki kartlar "
        "aranır). Hücre: ortalama [%95 bootstrap GA].",
        "",
        "| Mod | Recall@1 | Recall@5 | MRR |",
        "| --- | --- | --- | --- |",
    ]
    for m in modes:
        out.append(
            f"| {names[m]} | {fmt_ci([r[m + '@1'] for r in rows])} | {fmt_ci([r[m + '@5'] for r in rows])} | "
            f"{fmt_ci([r[m] for r in rows], pct=False)} |"
        )
    out += ["", "**Hibrit ile diğer modlar (sorgu başına ters sıra):**", ""]
    out += comparison_table(
        [
            (f"hibrit − {names[m].lower()}", [r["hybrid"] for r in rows], [r[m] for r in rows])
            for m in modes[1:]
        ],
        pct=False,
    )
    return out


def section_d4() -> list[str]:
    """Gerçek PR'lardaki çalıştırmalar (Action telemetrisi, `eval/d4.py topla`)."""
    path = Path("eval/datasets/d4.jsonl")
    if not path.is_file():
        return []
    rows = [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]
    prs = {(r["repo"], r["pr"]) for r in rows}
    durations = sorted(r["duration_seconds"] for r in rows)
    p95 = durations[min(len(durations) - 1, math.ceil(0.95 * len(durations)) - 1)]
    status = Counter(r["status"] for r in rows)
    band = Counter(r["risk_band"] for r in rows)
    repos = Counter(r["repo"] for r in rows)
    with_findings = sum(1 for r in rows if r["findings"])
    up = sum(r["thumbs_up"] for r in {(r["repo"], r["pr"]): r for r in rows}.values())
    down = sum(r["thumbs_down"] for r in {(r["repo"], r["pr"]): r for r in rows}.values())
    labels = {
        "skipped-low-risk": "düşük risk, LLM'e gönderilmedi",
        "skipped-no-llm": "LLM kapalı (runner'da Ollama yok)",
        "llm-error": "LLM'e ulaşılamadı (fail-open)",
        "ok": "LLM incelemesi tamamlandı",
    }
    return [
        "## 6. Gerçek PR'larda çalıştırma (D4)",
        "",
        f"{len(rows)} Action çalıştırması, {len(prs)} PR ("
        + ", ".join(f"{repo}: {n}" for repo, n in sorted(repos.items()))
        + "). Kaynak: Action'ın yüklediği `runs.jsonl` kayıtları (`eval/d4.py`, artifact'lar 90 gün "
        "saklanır). GitHub runner'larında Ollama olmadığı için LLM incelemesi bu çalıştırmalarda "
        "yoktur; süreler gatekeeper, hafıza ve deterministik denetimleri kapsar.",
        "",
        "| Ölçü | Değer |",
        "| --- | --- |",
        *(f"| {labels.get(k, k)} | {n} |" for k, n in status.most_common()),
        f"| Risk bandı (düşük / orta / yüksek) | {band['low']} / {band['medium']} / {band['high']} |",
        f"| Süre: medyan / p95 / en uzun | {num(median(durations), 2)} / {num(p95, 2)} / "
        f"{num(durations[-1], 2)} sn |",
        f"| Bulgu üreten çalıştırma (deterministik denetimler) | {with_findings} |",
        f"| Özet yorumuna tepki (👍 / 👎) | {up} / {down} |",
        "",
        "Hiçbir çalıştırma PR'ı engellemedi"
        + (
            f"; LLM'e ulaşılamayan {status['llm-error']} çalıştırma da uyarıyla tamamlandı."
            if status["llm-error"]
            else "."
        ),
    ]


def main() -> None:
    parts = [
        "# Sonuçlar (LLM'siz)",
        "",
        "> Bu belge `eval/results.py` ile üretilir; elle düzenlemeyin. LLM gerektiren deneyler "
        "(ucuz LLM triage #67, LLM'li RQ2, RQ4) burada yok. Yöntem ayrıntıları ve sınırlamalar "
        "`docs/architecture.md` ve `docs/mining-schema.md` içinde.",
        "",
    ]
    for section in (
        section_data,
        section_labels,
        section_models,
        section_rq1,
        section_rq2,
        section_d4,
    ):
        parts += section() + [""]
    parts += [
        "## 7. Geçerlilik notları",
        "",
        "- Etiketler SZZ'ye dayanır; elle kontrolde SZZ eşlemelerinin yalnızca ~%31'i doğru çıktı. "
        "Tüm RQ1 ve RQ2 sayıları bu gürültülü etiketlere göredir. Issue etiketi, taşınan satır ve "
        "tarih süzgeçleri bu veride doğruluğu artırmadı ya da veriyi yok etti "
        "(`docs/mining-schema.md`, SZZ süzgeçleri).",
        "- Etiket kalitesi setlerini (#8, #9) tek kişi, iki öneri setini görerek etiketledi; "
        "kararların büyük çoğunluğu önerilerle aynı (`docs/mining-schema.md`).",
        "- Hafızanın vektör kolu nöral değil LSA'dır (yerel LLM kurulmadı).",
        "- Fix sınıflandırıcısı aynı 200 commit üzerinde ayarlandı; precision/recall iyimserdir.",
    ]
    OUT.write_text("\n".join(parts) + "\n", "utf-8")
    print(f"→ {OUT}")


if __name__ == "__main__":
    main()
