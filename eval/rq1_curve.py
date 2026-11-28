"""RQ1 ilk sonuçları: maliyet–recall eğrisi ve iki işletme noktası (#21).

"PR'ların %X'i LLM'e gider → hatalı PR'ların %Y'si yakalanır" eğrisi PR düzeyinde çizilir.
Değerlendirme kayan pencerelidir (rolling-origin): her reponun PR'larının son yarısı 5 ardışık
pencereye bölünür; her pencerede modeller yalnızca pencere başlangıcından (90 gün tampon dahil)
önceki commit'lerle eğitilir. RF ve LightGBM 5 tohumla eğitilip ortalanır.

Yöntemler (hepsi aynı PR'ları puanlar):
- `lr`, `rf`, `lightgbm`: commit modeli, PR skoru `1 − Π(1 − pᵢ)` (çalışma anındaki yöntem, #66),
- `heuristic`: Faz 1'deki sezgisel kural (değişen satır + riskli yol), config ağırlıklarıyla,
- `random`: rastgele seçim; beklenen recall = gönderilen pay (köşegen).

İşletme noktaları gerçek kullanımdaki gibi seçilir: eşik bir önceki pencerenin PR skorlarından
belirlenir (bkz. #66, son PR'lardan bütçe eşiği), mevcut pencerede ölçülür.
- **maliyet odaklı:** önceki pencerede PR'ların %40'ı LLM'e gidecek eşik (~%60 eleme),
- **güvenlik odaklı:** önceki pencerede (o an bilinen etiketlerle) recall ≥ %90 veren en yüksek
  eşik.

Kullanım:
    uv run python eval/rq1_curve.py [.aegis/data] [eval/reports/rq1]
"""

import json
import math
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean, stdev
from typing import Any

import numpy as np
import polars as pl
from scipy.stats import wilcoxon

from aegis.config import AegisConfig, TrainingConfig
from aegis.gatekeeper.calibration import pr_score, recall_threshold
from aegis.gatekeeper.model import FEATURES, FULL_FEATURES, MEMORY_FEATURES, train_model
from aegis.gatekeeper.split import labels_as_of, rolling_windows, split_before

SHARES = [round(x, 2) for x in np.linspace(0, 1, 21)]
METHODS = ("lr", "lr+", "lr+m", "lr+mp", "rf+", "rf+m", "rf+mp", "heuristic")
"""`+`: Kamei + riskli yol + test oranı; `+m`: ayrıca hafıza sinyali (#29); `@5y`: yalnızca
pencereden önceki son 5 yılla eğitim (ör. `lr+@5y`); `+mp`: hafıza plasebosu — hafıza özellikleri
commit'ler arasında karıştırılır (dağılım aynı, bilgi yok), kazancın içerikten geldiğini sınar.
LightGBM ve 5 yıl #21/#8 koşularında ölçüldü."""
SHOWN = ("lr+", "lr+m", "lr+mp", "rf+m", "heuristic")
"""Eğride çizilen yöntemler (okunabilirlik için)."""
SEEDS = (0, 1, 2, 3, 4)
MIN_PRS = 200
COST_SHARE, SAFETY_RECALL = 0.4, 0.9
SAFETY_RULES = {
    "safety-k2": "Son 2 pencere, hedef recall %90",
    "safety-k3": "Son 3 pencere, hedef recall %90",
    "safety-95": "Son pencere, hedef recall %95",
    "safety-known": "90 gün olgunlaşmış etiketler, hedef recall %90",
}
"""Güvenlik eşiği alternatifleri (#107); eşikler yalnızca test penceresinden önceki PR'lardan."""
SAFETY_METHODS = ("lr+m", "heuristic")
SAFETY_SELECTION_NOTE = (
    "En iyi kural, aynı test pencerelerinin sonuçlarına bakılarak seçilir (ortalama recall "
    "≥ %90 olanlar içinde en yüksek eleme); bu seçim iyimserdir ve yeni veride doğrulanmamıştır."
)


def safety_rows(
    records: list[dict[str, Any]],
) -> list[tuple[str, str, list[float], list[float]]]:
    """Her güvenlik kuralı × yöntem için (kural başlığı, yöntem, eleme, recall) pencere listeleri."""
    if not records or "safety-k2" not in records[0][SAFETY_METHODS[0]]:
        raise SystemExit(
            "curves.json güvenlik eşiği alternatiflerini içermiyor (eski sürüm); "
            "önce `uv run python eval/rq1_curve.py` ile yeniden üretin"
        )
    return [
        (
            title,
            name,
            [1 - r[name][point][1] for r in records],
            [r[name][point][2] for r in records],
        )
        for point, title in SAFETY_RULES.items()
        for name in SAFETY_METHODS
        if name in records[0]
    ]


def best_safety_rule(
    rows: list[tuple[str, str, list[float], list[float]]],
) -> tuple[str, str, list[float], list[float]] | None:
    """Ortalama recall'ı hedefi tutan satırlar içinde ortalama elemesi en yüksek olan."""
    eligible = [
        row
        for row in rows
        if (known := [v for v in row[3] if not math.isnan(v)]) and mean(known) >= SAFETY_RECALL
    ]
    return max(eligible, key=lambda row: mean(row[2])) if eligible else None
_WORD = re.compile(r"[^a-z0-9]+")


def order(score: np.ndarray, seed: int = 0) -> np.ndarray:
    """Azalan skor sırası; eşitlikler sabit tohumlu rastgele kırılır (ör. sezgisel kural)."""
    jitter = np.random.default_rng(seed).random(len(score)) * 1e-9
    return np.argsort(-(score + jitter), kind="stable")


def curve(y: np.ndarray, score: np.ndarray) -> list[float]:
    """Her paydaki recall: PR'ların en riskli `pay` kadarı LLM'e giderse yakalanan hatalı payı."""
    if y.sum() == 0:
        return [math.nan] * len(SHARES)
    hits = np.concatenate([[0], np.cumsum(y[order(score)])])
    return [float(hits[math.ceil(s * len(y))] / y.sum()) for s in SHARES]


def apply(threshold: float, y: np.ndarray, score: np.ndarray) -> tuple[float, float]:
    """(LLM'e giden pay, recall) — `skor ≥ eşik` olan PR'lar gönderilir."""
    sent = score >= threshold
    return float(sent.mean()), float(sent[y].mean()) if y.any() else math.nan


def cost_threshold(prev: np.ndarray) -> float:
    """Önceki pencerede payı en fazla %40 olan en küçük eşik."""
    values = np.unique(prev)
    share = np.array([(prev >= v).mean() for v in values])
    ok = values[share <= COST_SHARE + 1e-12]
    return float(ok[0]) if ok.size else float(np.nextafter(prev.max(), np.inf))


def safety_threshold(prev: np.ndarray, y_prev: np.ndarray) -> float:
    """Önceki pencerede recall ≥ %90 veren en yüksek eşik (bilinen hata yoksa hepsi gider)."""
    return recall_threshold(prev, y_prev, SAFETY_RECALL)


def heuristic_scores(
    prs: pl.DataFrame, paths: dict[str, list[str]], cfg: AegisConfig
) -> np.ndarray:
    h = cfg.gatekeeper.heuristic
    risky = {p.lower() for p in h.risky_paths}
    out = []
    for la, ld, commits in prs.select("la", "ld", "commits").iter_rows():
        size = min(1.0, (la + ld) / h.size_saturation)
        words = {w for s in commits for p in paths.get(s, []) for w in _WORD.split(p.lower())}
        path = 1.0 if words & risky else 0.0
        out.append((h.size_weight * size + h.path_weight * path) / (h.size_weight + h.path_weight))
    return np.array(out)


def model_scores(
    name: str,
    commits: pl.DataFrame,
    start: datetime,
    cfg: TrainingConfig,
    groups: list[pl.DataFrame],
) -> list[np.ndarray]:
    """Her PR grubu için commit modeli → PR skorları (RF/LightGBM: tohumlar üzerinden ortalama)."""
    base, _, window = name.partition("@")
    placebo = base.endswith("+mp")
    if placebo:
        base = base.removesuffix("p")
    if base.endswith("+m"):
        features = MEMORY_FEATURES
    elif base.endswith("+"):
        features = FULL_FEATURES
    else:
        features = FEATURES
    model_name = base.removesuffix("+m").rstrip("+")
    if window == "5y":
        commits = commits.filter(pl.col("as_of") >= start - timedelta(days=round(5 * 365.25)))
    if placebo:
        # Hafıza değerleri commit'ler arasında sabit tohumla karıştırılır (eğitim ve puanlama).
        rng = np.random.default_rng(SEEDS[0])
        perm = rng.permutation(commits.height)
        commits = commits.with_columns(
            [commits[c].gather(perm).alias(c) for c in ("mem_func_bugs", "mem_file_bugs")]
        )
    split = split_before(commits, start, cfg)
    needed = {s for g in groups for c in g["commits"] for s in c}
    rows = commits.filter(pl.col("sha").is_in(needed))
    seeds = (0,) if model_name == "lr" else SEEDS
    probs: list[dict[str, float]] = []
    for seed in seeds:
        model = train_model(split, model_name, seed=seed, features=features)  # type: ignore[arg-type]
        probs.append(dict(zip(rows["sha"], model.predict_proba(rows), strict=True)))
    return [
        np.mean(
            [[pr_score([p[s] for s in members]) for members in g["commits"]] for p in probs],
            axis=0,
        )
        for g in groups
    ]


def evaluate_repo(
    repo: str, prs: pl.DataFrame, commits: pl.DataFrame, paths: dict[str, list[str]]
) -> list[dict[str, Any]]:
    cfg, acfg = TrainingConfig(), AegisConfig()
    out = []
    for w, (start, end) in enumerate(rolling_windows(prs, 5, 0.5)):
        test = prs.filter((pl.col("as_of") >= start) & (pl.col("as_of") < end))
        prev = prs.filter(pl.col("as_of") < start).tail(test.height)
        history = prs.filter(pl.col("as_of") < start).tail(test.height * 3)
        known_cutoff = start - timedelta(days=cfg.label_delay_days)
        matured = prs.filter(pl.col("as_of") < known_cutoff)
        y, y_prev = test["buggy"].to_numpy(), labels_as_of(prev, start)["buggy"].to_numpy()
        y_history = labels_as_of(history, start)["buggy"].to_numpy()
        known = matured.tail(test.height * 3)
        y_known = labels_as_of(known, known_cutoff)["buggy"].to_numpy()
        record: dict[str, Any] = {"repo": repo, "window": w, "n": test.height, "pos": int(y.sum())}
        for name in METHODS:
            if name == "heuristic":
                score, prev_score, history_score, known_score = (
                    heuristic_scores(test, paths, acfg),
                    heuristic_scores(prev, paths, acfg),
                    heuristic_scores(history, paths, acfg),
                    heuristic_scores(known, paths, acfg),
                )
            else:
                score, prev_score, history_score, known_score = model_scores(
                    name, commits, start, cfg, [test, prev, history, known]
                )
            c_thr, s_thr = cost_threshold(prev_score), safety_threshold(prev_score, y_prev)
            points = {
                "curve": curve(y, score),
                "cost": [c_thr, *apply(c_thr, y, score)],
                "safety": [s_thr, *apply(s_thr, y, score)],
            }
            policies = {
                "safety-k2": (
                    history_score[-min(len(history_score), 2 * test.height) :],
                    y_history[-min(len(y_history), 2 * test.height) :],
                    SAFETY_RECALL,
                ),
                "safety-k3": (history_score, y_history, SAFETY_RECALL),
                "safety-95": (prev_score, y_prev, 0.95),
                "safety-known": (known_score, y_known, SAFETY_RECALL),
            }
            for key, (cal_scores, cal_labels, target) in policies.items():
                threshold = recall_threshold(cal_scores, cal_labels, target)
                points[key] = [threshold, *apply(threshold, y, score)]
            record[name] = points
        out.append(record)
        print(f"{repo} pencere {w}: {test.height} PR, {int(y.sum())} hatalı", file=sys.stderr)
    return out


def fmt(values: list[float], pct: bool = False) -> str:
    vals = [v for v in values if not math.isnan(v)]
    if not vals:
        return "–"
    m, s = mean(vals), stdev(vals) if len(vals) > 1 else 0.0
    return f"%{100 * m:.0f} ± {100 * s:.0f}" if pct else f"{m:.2f} ± {s:.2f}"


def report(records: list[dict[str, Any]]) -> str:
    lines = ["## Maliyet–recall eğrisi (PR düzeyinde; repo × pencere ortalaması ± sapma)\n"]
    shown = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]
    lines.append("| Yöntem | " + " | ".join(f"%{100 * s:.0f} LLM" for s in shown) + " |")
    lines.append("| --- |" + " --- |" * len(shown))
    for name in (*METHODS, "random"):
        cells = []
        for s in shown:
            i = SHARES.index(s)
            vals = (
                [s] * len(records) if name == "random" else [r[name]["curve"][i] for r in records]
            )
            cells.append(fmt(vals))
        lines.append(f"| {name} | " + " | ".join(cells) + " |")

    lines.append("\n## İşletme noktaları (eşik önceki pencereden, ölçüm mevcut pencerede)\n")
    lines.append("| Nokta | Yöntem | Eşik | Eleme (LLM'e gitmeyen) | Recall |")
    lines.append("| --- | --- | --- | --- | --- |")
    for point, title in (
        ("cost", "maliyet odaklı (hedef %60 eleme)"),
        ("safety", "güvenlik odaklı (hedef ≥ %90 recall)"),
    ):
        for name in METHODS:
            thr = [r[name][point][0] for r in records]
            elim = [1 - r[name][point][1] for r in records]
            rec = [r[name][point][2] for r in records]
            lines.append(
                f"| {title} | {name} | {fmt(thr)} | {fmt(elim, True)} | {fmt(rec, True)} |"
            )

    lines.append("\n## Güvenlik eşiği alternatifleri (aynı pencereler)")
    lines.append("\n| Kural | Yöntem | Eleme | Gerçekleşen recall |")
    lines.append("| --- | --- | --- | --- |")
    rows = safety_rows(records)
    for title, name, elimination, recall in rows:
        lines.append(f"| {title} | {name} | {fmt(elimination, True)} | {fmt(recall, True)} |")
    best = best_safety_rule(rows)
    if best:
        title, name, elimination, recall = best
        lines.append(
            f"| **En iyi gözlenen: {title}** | **{name}** | **{fmt(elimination, True)}** | "
            f"**{fmt(recall, True)}** |"
        )
    else:
        lines.append("| En iyi gözlenen | – | – | Hiçbir kural ortalama %90'a ulaşmadı |")
    lines.append(f"\n{SAFETY_SELECTION_NOTE}")

    lines.append(
        "\n## Wilcoxon işaretli sıra testi (repo × pencere eşleştirmeli, %40 LLM payında recall)\n"
    )
    lines.append("| Karşılaştırma | Ortalama fark | p |")
    lines.append("| --- | --- | --- |")
    i = SHARES.index(COST_SHARE)
    for a, b in (
        ("lr+m", "heuristic"),
        ("rf+m", "heuristic"),
        ("lr+m", "lr+"),
        ("rf+m", "rf+"),
        ("lr+mp", "lr+"),
        ("rf+mp", "rf+"),
        ("lr+m", "lr+mp"),
        ("rf+m", "rf+mp"),
    ):
        pairs = [(r[a]["curve"][i], r[b]["curve"][i]) for r in records]
        pairs = [(x, z) for x, z in pairs if not (math.isnan(x) or math.isnan(z))]
        diff = [x - z for x, z in pairs]
        p = wilcoxon([x for x, _ in pairs], [z for _, z in pairs]).pvalue if any(diff) else 1.0
        lines.append(f"| {a} − {b} | {mean(diff):+.3f} | {p:.3g} |")

    lines.append("\n## Repo bazında (%40 LLM payında recall, pencere ortalaması)\n")
    lines.append("| Repo | Pencere × PR (hatalı) | " + " | ".join(METHODS) + " |")
    lines.append("| --- | --- |" + " --- |" * len(METHODS))
    for repo in sorted({r["repo"] for r in records}):
        rs = [r for r in records if r["repo"] == repo]
        size = f"{len(rs)} × ~{round(mean(r['n'] for r in rs))} ({sum(r['pos'] for r in rs)})"
        lines.append(
            f"| {repo} | {size} | "
            + " | ".join(fmt([r[m]["curve"][i] for r in rs]) for m in METHODS)
            + " |"
        )
    return "\n".join(lines) + "\n"


COLORS = {
    "lr": "#2563eb",
    "rf": "#059669",
    "lightgbm": "#d97706",
    "lr+": "#7c3aed",
    "rf+": "#0d9488",
    "lightgbm+": "#ca8a04",
    "lr+@5y": "#db2777",
    "lr+m": "#be185d",
    "rf+m": "#047857",
    "lr+mp": "#a8a29e",
    "rf+mp": "#d6d3d1",
    "heuristic": "#dc2626",
    "random": "#9a9a9a",
}


def _line(x1: float, y1: float, x2: float, y2: float, color: str, dash: str) -> str:
    return (
        f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
        f'stroke="{color}" stroke-dasharray="{dash}"/>'
    )


def _panel(x0: float, y0: float, size: int, title: str, rs: list[dict[str, Any]]) -> list[str]:
    def px(v: float) -> float:
        return x0 + v * size

    def py(v: float) -> float:
        return y0 + (1 - v) * size

    parts = [
        f'<rect x="{x0}" y="{y0}" width="{size}" height="{size}" fill="none" stroke="#ccc"/>',
        f'<text x="{px(0.5)}" y="{y0 - 10}" text-anchor="middle" font-size="13" '
        f'font-weight="600">{title}</text>',
        _line(px(COST_SHARE), py(0), px(COST_SHARE), py(1), "#bbb", "3 3"),
        _line(px(0), py(SAFETY_RECALL), px(1), py(SAFETY_RECALL), "#bbb", "3 3"),
        _line(px(0), py(0), px(1), py(1), COLORS["random"], "4 4"),
    ]
    for t in (0, 0.5, 1):
        parts.append(
            f'<text x="{px(t)}" y="{py(0) + 14}" text-anchor="middle" font-size="10">{t:g}</text>'
        )
        parts.append(
            f'<text x="{x0 - 6}" y="{py(t) + 3}" text-anchor="end" font-size="10">{t:g}</text>'
        )
    for name in SHOWN:
        m = np.nanmean([r[name]["curve"] for r in rs], axis=0)
        s = np.nanstd([r[name]["curve"] for r in rs], axis=0)
        upper = [f"{px(x):.1f},{py(min(1, v)):.1f}" for x, v in zip(SHARES, m + s, strict=True)]
        lower = [f"{px(x):.1f},{py(max(0, v)):.1f}" for x, v in zip(SHARES, m - s, strict=True)]
        band = " ".join(upper + lower[::-1])
        parts.append(f'<polygon points="{band}" fill="{COLORS[name]}" opacity="0.10"/>')
        pts = " ".join(f"{px(x):.1f},{py(v):.1f}" for x, v in zip(SHARES, m, strict=True))
        parts.append(
            f'<polyline points="{pts}" fill="none" stroke="{COLORS[name]}" stroke-width="2"/>'
        )
    return parts


def svg(records: list[dict[str, Any]]) -> str:
    """Repo başına bir panel + tüm repoların ortalaması; ortalama eğri ve ±1 sapma bandı."""
    groups = {"tüm repolar": records} | {
        r: [x for x in records if x["repo"] == r] for r in sorted({x["repo"] for x in records})
    }
    size, pad, gap, cols = 230, 36, 24, 3
    cell = size + 2 * pad + gap
    rows = math.ceil(len(groups) / cols)
    width, height = cols * cell, rows * cell + 60
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        'font-family="sans-serif">',
        '<rect width="100%" height="100%" fill="white"/>',
    ]
    for k, (title, rs) in enumerate(groups.items()):
        parts += _panel((k % cols) * cell + pad, (k // cols) * cell + pad, size, title, rs)
    y = rows * cell + 22
    x = 20.0
    for name in (*SHOWN, "random"):
        color = COLORS[name]
        parts.append(f'<rect x="{x}" y="{y - 9}" width="14" height="4" fill="{color}"/>')
        parts.append(f'<text x="{x + 20}" y="{y - 3}" font-size="12">{name}</text>')
        x += 120
    parts.append(
        f'<text x="20" y="{y + 20}" font-size="11" fill="#555">'
        "x: LLM'e giden PR payı · y: yakalanan hatalı PR payı · "
        "kesikli: %40 pay ve %90 recall · bant: ±1 sapma (repo × pencere)</text>"
    )
    parts.append("</svg>")
    return "\n".join(parts)


def main() -> None:
    data = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".aegis/data")
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("eval/reports/rq1")
    d1_path = Path(sys.argv[3]) if len(sys.argv) > 3 else data / "d1.parquet"
    prs_path = Path(sys.argv[4]) if len(sys.argv) > 4 else data / "d1-pr.parquet"
    d1, prs = pl.read_parquet(d1_path), pl.read_parquet(prs_path)
    records: list[dict[str, Any]] = []
    for repo in sorted(set(prs["repo"])):
        repo_prs = prs.filter(pl.col("repo") == repo)
        if repo_prs.height < MIN_PRS:
            print(f"{repo}: {repo_prs.height} PR < {MIN_PRS}, atlandı", file=sys.stderr)
            continue
        files = pl.read_parquet(data / repo / "files.parquet")
        paths = {
            sha: [p for p in ps if p]
            for sha, ps in files.group_by("sha")
            .agg(pl.coalesce("new_path", "old_path"))
            .iter_rows()
        }
        records += evaluate_repo(repo, repo_prs, d1.filter(pl.col("repo") == repo), paths)
    out.mkdir(parents=True, exist_ok=True)
    (out / "curves.json").write_text(json.dumps(records, indent=1, default=str), "utf-8")
    (out / "rq1.md").write_text(report(records), "utf-8")
    (out / "curve.svg").write_text(svg(records), "utf-8")
    print(report(records))


if __name__ == "__main__":
    main()
