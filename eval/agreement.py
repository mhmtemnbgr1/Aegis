"""Etiketleme sonuçları: etiketleyiciler arası uyuşma (Cohen's κ) ve doğruluk ölçümleri (#8, #9).

Girdi: inceleme sayfasından indirilen CSV (`correct` = son karar, `suggested_<ad>` = öneri
seti). Son kararlar öneriler sayfada görülerek verildi.

- `szz`: SZZ eşlemesi doğruluğu = evet / (evet + hayır), son karara göre; repo bazında da.
- `fix`: sınıflandırıcının (fix-sample.csv'deki `classifier`) precision ve recall değeri, son
  karara göre. Örneklem yarı yarıya tabakalı olduğu için recall, tabakaların repo içindeki
  gerçek paylarıyla ağırlıklandırılarak da verilir.

Kullanım:
    uv run python eval/agreement.py szz eval/labels/szz-kontrol.csv
    uv run python eval/agreement.py fix eval/labels/fix-kontrol.csv
"""

import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

import polars as pl

LABELS = ("evet", "hayir", "belirsiz")


def kappa(a: list[str], b: list[str]) -> float:
    n = len(a)
    observed = sum(x == y for x, y in zip(a, b, strict=True)) / n
    ca, cb = Counter(a), Counter(b)
    expected = sum(ca[c] / n * cb[c] / n for c in LABELS)
    return 1.0 if expected == 1 else (observed - expected) / (1 - expected)


def agreement(rows: pl.DataFrame) -> list[str]:
    raters = {"karar": rows["correct"].to_list()} | {
        c.removeprefix("suggested_"): rows[c].to_list()
        for c in rows.columns
        if c.startswith("suggested_")
    }
    out = ["| Çift | Aynı karar | Cohen's κ |", "| --- | --- | --- |"]
    for (na, a), (nb, b) in combinations(raters.items(), 2):
        same = sum(x == y for x, y in zip(a, b, strict=True))
        out.append(f"| {na} – {nb} | {same}/{len(a)} | {kappa(a, b):.2f} |")
    counts = ", ".join(f"{k} {v}" for k, v in sorted(Counter(raters["karar"]).items()))
    return [f"Son kararlar: {counts}", "", *out]


def szz(rows: pl.DataFrame) -> list[str]:
    sample = pl.read_csv("eval/labels/szz-sample.csv", infer_schema=False).select(
        "fix_sha", "inducing_sha", "repo"
    )
    rows = rows.join(sample, on=["fix_sha", "inducing_sha"], how="left")
    out = ["", "## SZZ doğruluğu (son karara göre; belirsizler hariç)", ""]
    out += ["| Kapsam | Evet | Hayır | Belirsiz | Doğruluk |", "| --- | --- | --- | --- | --- |"]
    for name, part in [("tümü", rows), *sorted(rows.group_by("repo"), key=lambda g: g[0])]:
        c = Counter(part["correct"].to_list())
        decided = c["evet"] + c["hayir"]
        acc = f"%{100 * c['evet'] / decided:.0f}" if decided else "–"
        label = name if isinstance(name, str) else name[0]
        out.append(f"| {label} | {c['evet']} | {c['hayir']} | {c['belirsiz']} | {acc} |")
    return out


def fix(rows: pl.DataFrame) -> list[str]:
    sample = pl.read_csv("eval/labels/fix-sample.csv", infer_schema=False).select(
        "repo", "sha", pl.col("classifier") == "true"
    )
    rows = rows.join(sample, on=["repo", "sha"], how="left").filter(pl.col("correct") != "belirsiz")
    truth = rows["correct"] == "evet"
    pred = rows["classifier"]
    tp = int((truth & pred).sum())
    fp = int((~truth & pred).sum())
    fn = int((truth & ~pred).sum())
    out = ["", "## Fix sınıflandırıcısı (son karara göre; belirsizler hariç)", ""]
    out.append(f"- Precision: {tp}/{tp + fp} = %{100 * tp / max(tp + fp, 1):.0f}")
    out.append(
        f"- Recall (tabakalı örneklemde): {tp}/{tp + fn} = %{100 * tp / max(tp + fn, 1):.0f}"
    )
    # Gerçek recall: fix-olmayan tabakadaki kaçırılan fix oranı, repodaki fix-olmayan sayısıyla
    # ağırlıklandırılır (tabakalar eşit büyüklükte örneklendi).
    weighted_tp = weighted_fn = 0.0
    for (repo,), part in rows.group_by("repo"):
        commits = pl.read_parquet(Path(".aegis/data") / repo / "commits.parquet")
        d1 = pl.read_parquet(".aegis/data/d1.parquet").filter(pl.col("repo") == repo)
        pop = commits.join(d1.select("sha"), on="sha")
        n_fix, n_other = int(pop["is_fix"].sum()), int((~pop["is_fix"]).sum())
        pos, neg = part.filter(pl.col("classifier")), part.filter(~pl.col("classifier"))
        if pos.height:
            weighted_tp += n_fix * (pos["correct"] == "evet").mean()  # type: ignore[operator]
        if neg.height:
            weighted_fn += n_other * (neg["correct"] == "evet").mean()  # type: ignore[operator]
    if weighted_tp + weighted_fn:
        rec = weighted_tp / (weighted_tp + weighted_fn)
        out.append(f"- Recall (popülasyona ağırlıklı tahmin): %{100 * rec:.0f}")
    return out


def main() -> None:
    kind, path = sys.argv[1], Path(sys.argv[2])
    rows = pl.read_csv(path, infer_schema=False).with_columns(pl.col("correct").fill_null(""))
    missing = rows.filter(~pl.col("correct").is_in(LABELS)).height
    if missing:
        sys.exit(f"{missing} madde etiketsiz; önce hepsini etiketleyin.")
    lines = [f"# {kind} etiketleme sonuçları ({rows.height} madde)", "", *agreement(rows)]
    lines += szz(rows) if kind == "szz" else fix(rows)
    print("\n".join(lines))


if __name__ == "__main__":
    main()
