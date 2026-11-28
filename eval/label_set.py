"""Doğrulama setini büyütmek (#108): örneklem, inceleme sayfası, uyum, birleştirme ve sonuç.

Üç tür örnek, 6 D1 reposundan tabakalı ve sabit tohumla:

- **szz** (repo başına 25 = 150): D1'in hatalı (SZZ pozitifi) commit'leri; her biri için rastgele
  bir düzelten commit. Soru: bu commit, düzelten commit'in giderdiği hatayı gerçekten getiriyor mu?
- **fix** (repo başına 10 = 60): D2'nin tersine çevrilmiş düzeltmeleri (`revert: true`). Soru: bu
  commit gerçekten bir hata düzeltmesi mi?
- **clean** (repo başına 10 = 60): D2'nin temiz commit'leri. Soru: değişiklikte hata var mı?

Daha önce kontrol edilen örnekler (`szz-sample.csv`, `d2-sample.csv`) dışarıda bırakılır.

    # 1. Örneklem → eval/labels/dogrulama-sample.csv
    uv run python eval/label_set.py ornekle

    # 2. Tek dosyalık inceleme sayfası (klonlar gerekir) → eval/labels/dogrulama-review.html
    uv run python eval/label_set.py sayfa

    # 3. İki etiket seti sayfadaki "CSV indir" ile etiket-seti-<n>.csv olarak alınır:
    uv run python eval/label_set.py uyum eval/labels/etiket-seti-3.csv eval/labels/etiket-seti-4.csv

    # 4. Aynı cevaplı örnekler son etiket olur → eval/labels/dogrulanmis.csv
    uv run python eval/label_set.py birlestir \
        eval/labels/etiket-seti-3.csv eval/labels/etiket-seti-4.csv

    # 5. Doğruluk tabloları (Markdown, %95 Wilson GA)
    uv run python eval/label_set.py sonuc

Yönerge: `eval/dogrulama-etiketleme.md`.
"""

import csv
import json
import math
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import polars as pl

sys.path.insert(0, str(Path(__file__).parent))
from d2_labeling import kappa  # noqa: E402
from szz_review import build  # noqa: E402

from aegis.mining import github_repository  # noqa: E402
from aegis.mining.d2 import D2Sample, read_d2  # noqa: E402
from aegis.mining.gitfiles import git  # noqa: E402

D2 = Path("eval/datasets/d2.jsonl")
DATA, CLONES, LABELS = Path(".aegis/data"), Path(".aegis/repos"), Path("eval/labels")
SAMPLE, PAGE = LABELS / "dogrulama-sample.csv", LABELS / "dogrulama-review.html"
VERIFIED = LABELS / "dogrulanmis.csv"
TEMPLATE = Path(__file__).with_name("label_set_template.html")
PER_REPO = {"szz": 25, "fix": 10, "clean": 10}
SEED = 108
MAX_DIFF_CHARS = 20_000

ANSWERS = {
    "szz": ("dogru", "kismen", "yanlis", "belirsiz"),
    "fix": ("evet", "hayir", "belirsiz"),
    "clean": ("temiz", "hatali", "belirsiz"),
}
COLUMNS = ["no", "kind", "repo", "sha", "fix_sha", "answer", "note", "labeler"]


# --- Örneklem ---------------------------------------------------------------------------------
def _previous() -> tuple[set[str], set[str]]:
    """Önceki kontrollerde görülen inducing commit'ler ve D2 örnekleri."""
    inducing: set[str] = set()
    if (path := LABELS / "szz-sample.csv").is_file():
        inducing = {r["inducing_sha"] for r in csv.DictReader(path.open(encoding="utf-8"))}
    d2: set[str] = set()
    if (path := LABELS / "d2-sample.csv").is_file():
        d2 = {r["sha"] for r in csv.DictReader(path.open(encoding="utf-8"))}
    return inducing, d2


def _szz_pairs(repo: str) -> pl.DataFrame:
    """Repo'nun fix → inducing eşlemeleri (dosyalar birleştirilmiş)."""
    return (
        pl.read_parquet(DATA / repo / "szz.parquet")
        .group_by("fix_sha", "inducing_sha")
        .agg(pl.col("path").sort().str.join(", ").alias("paths"))
        .sort("inducing_sha", "fix_sha")
    )


def sample(seed: int = SEED) -> list[dict[str, str]]:
    rng = random.Random(seed)
    seen_inducing, seen_d2 = _previous()
    d1 = pl.read_parquet(DATA / "d1.parquet").filter(pl.col("buggy")).select("repo", "sha")
    d2 = read_d2(D2)
    chosen: list[dict[str, str]] = []
    for repo in sorted(set(d1["repo"])):
        positives = set(d1.filter(pl.col("repo") == repo)["sha"])
        pairs = _szz_pairs(repo)
        fixes: dict[str, list[str]] = {}
        for fix, inducing in pairs.select("fix_sha", "inducing_sha").iter_rows():
            if inducing in positives and inducing not in seen_inducing:
                fixes.setdefault(inducing, []).append(fix)
        for inducing in rng.sample(sorted(fixes), min(PER_REPO["szz"], len(fixes))):
            chosen.append(
                {
                    "kind": "szz",
                    "repo": repo,
                    "sha": inducing,
                    "fix_sha": rng.choice(fixes[inducing]),
                }
            )
        for kind, label in (("fix", "buggy"), ("clean", "clean")):
            pool = sorted(
                (s for s in d2 if s.repo == repo and s.label == label and s.sha not in seen_d2),
                key=lambda s: s.sha,
            )
            for s in rng.sample(pool, min(PER_REPO[kind], len(pool))):
                chosen.append(
                    {
                        "kind": kind,
                        "repo": repo,
                        "sha": s.sha,
                        "fix_sha": s.sha if kind == "fix" else "",
                    }
                )
    rng.shuffle(chosen)  # etiketleyici repo ya da tür sırasıyla karşılaşmasın
    return [{"no": str(i), **row} for i, row in enumerate(chosen, 1)]


def cmd_sample() -> None:
    rows = sample()
    with SAMPLE.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, ["no", "kind", "repo", "sha", "fix_sha"])
        w.writeheader()
        w.writerows(rows)
    counts = Counter(r["kind"] for r in rows)
    print(f"{len(rows)} örnek {dict(counts)} → {SAMPLE}")


# --- İnceleme sayfası -------------------------------------------------------------------------
def _base_url(repo: str) -> str:
    meta = json.loads((DATA / repo / "meta.json").read_text("utf-8"))
    gh = github_repository(meta["remote_url"])
    return f"https://github.com/{gh}/commit/" if gh else ""


def _szz_items(repo: str, rows: list[dict[str, str]]) -> dict[tuple[str, str], dict[str, Any]]:
    """`szz_review.build` ile eşleme görünümleri: fix'in sildiği satırlar ve inducing'deki hali."""
    commits = pl.read_parquet(DATA / repo / "commits.parquet").select(
        "sha", pl.col("message").str.split("\n").list.first().alias("subject"), "author_date"
    )
    info = {r["sha"]: r for r in commits.iter_rows(named=True)}
    paths = {(f, i): p for f, i, p in _szz_pairs(repo).iter_rows()}
    base = _base_url(repo)
    table = [
        {
            "fix_sha": r["fix_sha"],
            "inducing_sha": r["sha"],
            "paths": paths[(r["fix_sha"], r["sha"])],
            "fix_subject": info[r["fix_sha"]]["subject"],
            "inducing_subject": info[r["sha"]]["subject"],
            "fix_date": info[r["fix_sha"]]["author_date"].date().isoformat(),
            "inducing_date": info[r["sha"]]["author_date"].date().isoformat(),
            "fix_url": base + r["fix_sha"],
            "inducing_url": base + r["sha"],
        }
        for r in rows
    ]
    tmp = LABELS / f".dogrulama-{repo}.csv"
    pl.DataFrame(table).write_csv(tmp)
    try:
        built = build(DATA / repo, CLONES / repo, tmp)
    finally:
        tmp.unlink()
    return {(it["fix_sha"], it["inducing_sha"]): it for it in built}


def _commit(repo: str, sha: str) -> dict[str, str]:
    message = git(CLONES / repo, "log", "-1", "--format=%B", sha).strip()
    date = git(CLONES / repo, "log", "-1", "--format=%aI", sha).strip()[:10]
    return {"message": message, "date": date, "url": _base_url(repo) + sha}


def cmd_page() -> None:
    rows = list(csv.DictReader(SAMPLE.open(encoding="utf-8")))
    d2: dict[str, D2Sample] = {s.sha: s for s in read_d2(D2)}
    szz: dict[tuple[str, str], dict[str, Any]] = {}
    for repo in sorted({r["repo"] for r in rows if r["kind"] == "szz"}):
        szz |= _szz_items(repo, [r for r in rows if r["kind"] == "szz" and r["repo"] == repo])
    items = []
    for r in rows:
        item: dict[str, Any] = {k: r[k] for k in ("no", "kind", "repo", "sha", "fix_sha")}
        if r["kind"] == "szz":
            item["pair"] = szz[(r["fix_sha"], r["sha"])]
        else:
            item |= _commit(r["repo"], r["sha"])
            if r["kind"] == "fix":
                parent = d2[r["sha"]].parent
                diff = git(CLONES / r["repo"], "diff", "--no-color", "-M", parent, r["sha"])
            else:
                diff = d2[r["sha"]].diff
            item["diff"] = diff[:MAX_DIFF_CHARS]
            item["truncated"] = len(diff) > MAX_DIFF_CHARS
        items.append(item)
    data = json.dumps(items, ensure_ascii=False).replace("</", "<\\/")
    PAGE.write_text(TEMPLATE.read_text("utf-8").replace("__DATA__", data), "utf-8")
    empty = sum(1 for it in items if it["kind"] == "szz" and not it["pair"]["sections"])
    print(
        f"{len(items)} örnek → {PAGE} ({PAGE.stat().st_size // 1024} KB; satırı çıkmayan {empty})"
    )


# --- Uyum, birleştirme ve sonuç ---------------------------------------------------------------
def _load(path: Path) -> dict[str, dict[str, str]]:
    return {r["no"]: r for r in csv.DictReader(path.open(encoding="utf-8-sig"))}


def cmd_agreement(first: Path, second: Path) -> None:
    a, b = _load(first), _load(second)
    shared = [no for no in a if no in b and a[no]["answer"] and b[no]["answer"]]
    print(f"İki setin de yanıtladığı örnek: {len(shared)}")
    for kind in ANSWERS:
        keys = [no for no in shared if a[no]["kind"] == kind]
        x, y = [a[no]["answer"] for no in keys], [b[no]["answer"] for no in keys]
        same = sum(i == j for i, j in zip(x, y, strict=True))
        print(f"{kind}: {same}/{len(keys)} aynı · Cohen κ {kappa(x, y):.2f}")
    if diff := [no for no in shared if a[no]["answer"] != b[no]["answer"]]:
        print("\nFarklı cevaplar:")
        for no in diff:
            r = a[no]
            print(f"  {no:>3} {r['kind']:<5} {r['repo']} {r['sha'][:10]}: "
                  f"{r['answer']} / {b[no]['answer']}")  # fmt: skip


def verified_label(kind: str, answer: str) -> str:
    """Commit için doğrulanmış etiket: `buggy`, `clean` ya da boş (çıkarım yok).

    `szz` + yanlış boş kalır: commit bu düzeltmenin hatasını getirmiyor ama başka bir hatayı
    getiriyor olabilir. `fix` türü D2'nin tersine çevrilmiş örneğini doğrular, commit etiketi değil.
    """
    if kind == "szz" and answer in ("dogru", "kismen"):
        return "buggy"
    if kind == "clean":
        return {"temiz": "clean", "hatali": "buggy"}.get(answer, "")
    return ""


def cmd_merge(first: Path, second: Path) -> None:
    """İki setin aynı cevabı verdiği örnekler → dogrulanmis.csv (#109 için sha, repo, etiket)."""
    a, b = _load(first), _load(second)
    agreed = [
        r for no, r in a.items() if r["answer"] and b.get(no, {}).get("answer") == r["answer"]
    ]
    with VERIFIED.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["no", "kind", "repo", "sha", "fix_sha", "answer", "label"])
        for r in agreed:
            label = verified_label(r["kind"], r["answer"])
            w.writerow([r["no"], r["kind"], r["repo"], r["sha"], r["fix_sha"], r["answer"], label])
    counts = Counter((r["kind"], r["answer"]) for r in agreed)
    print(f"{len(agreed)} ortak etiket → {VERIFIED}: {dict(sorted(counts.items()))}")


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    """Binom oranı için %95 Wilson güven aralığı."""
    if n == 0:
        return math.nan, math.nan
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return centre - half, centre + half


def rate(k: int, n: int) -> str:
    if n == 0:
        return "–"
    lo, hi = wilson(k, n)
    pct = lambda x: f"{100 * x:.1f}".replace(".", ",")  # noqa: E731
    return f"{k}/{n} = %{pct(k / n)} [{pct(lo)}; {pct(hi)}]"


def summary(rows: list[dict[str, str]]) -> list[str]:
    """Belgeler için Markdown: tür başına doğruluk ve SZZ'nin repo bazında doğruluğu."""
    by = Counter((r["kind"], r["answer"]) for r in rows)
    szz_n = by["szz", "dogru"] + by["szz", "kismen"] + by["szz", "yanlis"]
    fix_n = by["fix", "evet"] + by["fix", "hayir"]
    clean_n = by["clean", "temiz"] + by["clean", "hatali"]
    out = [
        "| Tür | Ölçü | Oran [%95 GA] | Belirsiz |",
        "| --- | --- | --- | --- |",
        f"| SZZ hatalı commit | doğru | {rate(by['szz', 'dogru'], szz_n)} | "
        f"{by['szz', 'belirsiz']} |",
        f"| SZZ hatalı commit | doğru + kısmen | "
        f"{rate(by['szz', 'dogru'] + by['szz', 'kismen'], szz_n)} | |",
        f"| Tersine çevrilmiş düzeltme | gerçek düzeltme | {rate(by['fix', 'evet'], fix_n)} | "
        f"{by['fix', 'belirsiz']} |",
        f"| Temiz commit | temiz | {rate(by['clean', 'temiz'], clean_n)} | "
        f"{by['clean', 'belirsiz']} |",
        "",
        "| Repo | SZZ doğru + kısmen [%95 GA] |",
        "| --- | --- |",
    ]
    for repo in sorted({r["repo"] for r in rows if r["kind"] == "szz"}):
        part = Counter(r["answer"] for r in rows if r["kind"] == "szz" and r["repo"] == repo)
        n = part["dogru"] + part["kismen"] + part["yanlis"]
        out.append(f"| {repo} | {rate(part['dogru'] + part['kismen'], n)} |")
    return out


def cmd_summary() -> None:
    rows = list(csv.DictReader(VERIFIED.open(encoding="utf-8")))
    print("\n".join(summary(rows)))


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "ornekle":
        cmd_sample()
    elif cmd == "sayfa":
        cmd_page()
    elif cmd == "uyum" and len(sys.argv) == 4:
        cmd_agreement(Path(sys.argv[2]), Path(sys.argv[3]))
    elif cmd == "birlestir" and len(sys.argv) == 4:
        cmd_merge(Path(sys.argv[2]), Path(sys.argv[3]))
    elif cmd == "sonuc":
        cmd_summary()
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
