"""D2'nin elle etiketlenen alt kümesi (#69): örneklem, inceleme sayfası ve uyum.

    # 1. Örneklem: her D2 reposundan 10 hatalı + 7 temiz (≈100), sabit tohumla.
    uv run python eval/d2_labeling.py ornekle        # → eval/labels/d2-revert-sample.csv

    # 2. Tek dosyalık inceleme sayfası (klonlar gerekir; sayfa sonra her yerde açılır):
    uv run python eval/d2_labeling.py sayfa          # → eval/labels/d2-revert-review.html

    # 3. İki etiket seti, sayfadaki "CSV indir" ile d2-revert-kontrol-<ad>.csv olarak alınır:
    uv run python eval/d2_labeling.py uyum <etiket1.csv> <etiket2.csv>

`uyum`, Cohen κ'yı (hatalı ve temiz için ayrı ayrı) ve anlaşmazlıkları yazar. `birlestir`, iki
setin aynı cevabı verdiği örnekleri son etiket olarak
`eval/labels/d2-revert-kontrol.csv` dosyasına yazar (farklı cevaplı örnekler alt kümeye girmez):

    uv run python eval/d2_labeling.py birlestir \
        eval/labels/d2-revert-kontrol-1.csv eval/labels/d2-revert-kontrol-2.csv

Yönerge: `eval/d2-etiketleme.md`.
"""

import csv
import hashlib
import json
import random
import sys
from collections import Counter
from pathlib import Path

import polars as pl

from aegis.mining import github_repository
from aegis.mining.d2 import D2Sample, read_d2
from aegis.mining.gitfiles import git

D2 = Path("eval/datasets/d2.jsonl")
DATA, CLONES, LABELS = Path(".aegis/data"), Path(".aegis/repos"), Path("eval/labels")
SAMPLE, PAGE = LABELS / "d2-revert-sample.csv", LABELS / "d2-revert-review.html"
TEMPLATE = Path(__file__).with_name("d2_review_template.html")
PER_REPO = {"buggy": 10, "clean": 7}
MAX_FIX_CHARS = 8_000


def sample(seed: int = 0) -> list[D2Sample]:
    rng = random.Random(seed)
    chosen: list[D2Sample] = []
    samples = read_d2(D2)
    for repo in sorted({s.repo for s in samples}):
        for label, n in PER_REPO.items():
            pool = sorted(
                (s for s in samples if s.repo == repo and s.label == label), key=lambda s: s.sha
            )
            chosen += rng.sample(pool, min(n, len(pool)))
    rng.shuffle(chosen)  # etiketleyici repo ya da sınıf sırasıyla karşılaşmasın
    return chosen


def cmd_sample() -> None:
    chosen = sample()
    with SAMPLE.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["no", "repo", "sha", "label"])
        for i, s in enumerate(chosen, 1):
            w.writerow([i, s.repo, s.sha, s.label])
    counts = Counter(s.label for s in chosen)
    print(f"{len(chosen)} örnek ({counts['buggy']} hatalı, {counts['clean']} temiz) -> {SAMPLE}")


def _commit_url(repo: str, sha: str) -> str:
    meta = json.loads((DATA / repo / "meta.json").read_text("utf-8"))
    gh = github_repository(meta["remote_url"])
    return f"https://github.com/{gh}/commit/{sha}" if gh else ""


def cmd_page() -> None:
    by_sha = {s.sha: s for s in read_d2(D2)}
    rows = list(csv.DictReader(SAMPLE.open(encoding="utf-8")))
    items = []
    for row in rows:
        s = by_sha[row["sha"]]
        commits = pl.read_parquet(DATA / s.repo / "commits.parquet")
        info = {
            r["sha"]: r
            for r in commits.filter(pl.col("sha").is_in([s.sha, *s.fix_shas])).iter_rows(named=True)
        }
        fixes = []
        for fix in s.fix_shas:
            paths = sorted({e["path"] for e in s.expected})
            diff = git(CLONES / s.repo, "diff", "--no-color", "-M", f"{fix}^1", fix)
            fixes.append(
                {
                    "sha": fix,
                    "subject": info[fix]["message"].splitlines()[0],
                    "date": info[fix]["author_date"].date().isoformat(),
                    "url": _commit_url(s.repo, fix),
                    "diff": diff[:MAX_FIX_CHARS],
                    "paths": paths,
                }
            )
        items.append(
            {
                "repo": s.repo,
                "sha": s.sha,
                "label": s.label,
                "revert": s.revert,
                "subject": info[s.sha]["message"].splitlines()[0] if info[s.sha]["message"] else "",
                "date": s.date[:10],
                "url": _commit_url(s.repo, s.sha),
                "diff": s.diff,
                "expected": s.expected,
                "fixes": fixes,
            }
        )
    data = json.dumps(items, ensure_ascii=False).replace("</", "<\\/")
    dataset_id = hashlib.sha256("\n".join(row["sha"] for row in rows).encode()).hexdigest()[:12]
    html = (
        TEMPLATE.read_text("utf-8")
        .replace("__DATA__", data)
        .replace("__DATASET_ID__", dataset_id)
        .replace("__EXPORT_PREFIX__", "d2-revert")
    )
    PAGE.write_text(html, "utf-8")
    print(f"{len(items)} örnek -> {PAGE} ({PAGE.stat().st_size // 1024} KB)")


def kappa(a: list[str], b: list[str]) -> float:
    n = len(a)
    if n == 0:
        return float("nan")
    observed = sum(x == y for x, y in zip(a, b, strict=True)) / n
    ca, cb = Counter(a), Counter(b)
    expected = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / n**2
    return 1.0 if expected == 1 else (observed - expected) / (1 - expected)


def cmd_agreement(first: Path, second: Path) -> None:
    def load(p: Path) -> dict[str, dict[str, str]]:
        return {r["sha"]: r for r in csv.DictReader(p.open(encoding="utf-8-sig"))}

    a, b = load(first), load(second)
    shared = [sha for sha in a if sha in b and a[sha]["answer"] and b[sha]["answer"]]
    print(f"İki setin de yanıtladığı örnek: {len(shared)}")
    for label in ("buggy", "clean"):
        keys = [s for s in shared if a[s]["label"] == label]
        x, y = [a[s]["answer"] for s in keys], [b[s]["answer"] for s in keys]
        agree = sum(i == j for i, j in zip(x, y, strict=True))
        print(
            f"{label}: {agree}/{len(keys)} aynı · Cohen κ {kappa(x, y):.2f} · "
            f"{dict(Counter(x))} / {dict(Counter(y))}"
        )
    disagreements = [s for s in shared if a[s]["answer"] != b[s]["answer"]]
    if disagreements:
        print("\nAnlaşmazlıklar (konuşup d2-kontrol.csv'ye son etiketi yazın):")
        for s in disagreements:
            print(
                f"  {a[s]['no']:>3} {a[s]['repo']} {s[:10]} {a[s]['label']}: "
                f"{a[s]['answer']} / {b[s]['answer']}"
            )


def cmd_merge(first: Path, second: Path) -> None:
    """İki setin aynı cevabı verdiği örnekler → d2-kontrol.csv (labeler: ortak)."""

    def load(p: Path) -> list[dict[str, str]]:
        return list(csv.DictReader(p.open(encoding="utf-8-sig")))

    b = {r["sha"]: r for r in load(second)}
    agreed = [
        r for r in load(first) if r["answer"] and b.get(r["sha"], {}).get("answer") == r["answer"]
    ]
    marker = "-kontrol-"
    prefix = first.stem.partition(marker)[0] if marker in first.stem else "d2"
    out = LABELS / f"{prefix}-kontrol.csv"
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["no", "repo", "sha", "label", "answer", "note", "labeler"])
        for r in agreed:
            w.writerow([r["no"], r["repo"], r["sha"], r["label"], r["answer"], "", "ortak"])
    counts = Counter((r["label"], r["answer"]) for r in agreed)
    print(f"{len(agreed)} ortak etiket -> {out}: {dict(sorted(counts.items()))}")


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
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
