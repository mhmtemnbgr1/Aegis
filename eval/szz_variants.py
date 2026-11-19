"""SZZ doğruluğunu artırma fikirlerinin elle etiketli eşlemelerde ölçülmesi.

Elle kontrol edilen 50 eşlemede (#9, `eval/labels/szz-kontrol.csv`) SZZ'nin doğruluğu %31 çıktı.
Yanlışların yaklaşık üçte biri hata düzeltmesi olmayan "fix"lerden, kalanı düzeltmenin hatayla
ilgisiz satırlara dokunmasından geliyor. Bu betik üç süzgeci tek tek ve birlikte dener:

- `issue`: fix'in mesajı hata etiketli bir issue ya da PR'a bağlanıyor (etiket adında `bug` veya
  `regression` geçer). Hata düzeltmesi olmayan fix'leri hedefler.
- `taşıma`: `git blame -M -C`; taşınan ya da kopyalanan satırlar asıl yazıldıkları commit'e izlenir.
- `tarih`: hata getiren commit, bağlı issue'nun (PR değil) açılışından önce olmalı. Issue yoksa
  süzgeç uygulanmaz.

Her varyant için: kalan eşleme sayısı, doğruluk (kalanların doğru olanı) ve doğru eşlemelerin ne
kadarının korunduğu. `--hacim` ile ayrıca D1 repolarında `issue` süzgecinin fix ve hata getiren
commit sayısına etkisi ölçülür (tüm bağlı numaralar için GitHub'a sorulur; sonuçlar cache'lenir).

Issue bilgisi için GitHub token'ı gerekir (`GITHUB_TOKEN`). Cache: `.aegis/data/<repo>/issues.json`.

Kullanım:
    GITHUB_TOKEN=... uv run python eval/szz_variants.py [--hacim]
"""

import csv
import json
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl

from aegis.github.client import GitHubClient
from aegis.mining import github_repository, linked_issues
from aegis.mining.labels import github_issue_info
from aegis.mining.szz import _IGNORE_REVS_FILE, blame_lines, deleted_lines

DATA, REPOS, LABELS = Path(".aegis/data"), Path(".aegis/repos"), Path("eval/labels")
OUT = Path("eval/reports/szz-variants.md")


def is_bug_label(label: str) -> bool:
    name = label.lower()
    return "bug" in name or "regression" in name


class Issues:
    """Repo başına cache'li issue bilgisi."""

    def __init__(self, token: str) -> None:
        self.token = token
        self.sources: dict[str, Any] = {}

    def __call__(self, slug: str, numbers: list[int]) -> dict[int, dict[str, Any] | None]:
        if slug not in self.sources:
            meta = json.loads((DATA / slug / "meta.json").read_text("utf-8"))
            gh = github_repository(meta["remote_url"])
            if gh is None:
                raise SystemExit(f"{slug}: GitHub reposu değil")
            self.sources[slug] = github_issue_info(
                GitHubClient(self.token, gh), DATA / slug / "issues.json"
            )
        return dict(self.sources[slug](numbers))


def _when(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def pair_facts(row: dict[str, str], issues: Issues) -> dict[str, Any]:
    """Bir eşleme için süzgeçlerin kararları."""
    slug, fix, inducing = row["repo"], row["fix_sha"], row["inducing_sha"]
    commits = pl.read_parquet(DATA / slug / "commits.parquet").filter(
        pl.col("sha").is_in([fix, inducing])
    )
    by_sha = {r["sha"]: r for r in commits.iter_rows(named=True)}
    numbers = list(linked_issues(by_sha[fix]["message"]))
    info = issues(slug, numbers)
    linked = [i for i in info.values() if i is not None]
    bug = any(is_bug_label(lbl) for i in linked for lbl in i["labels"])
    reports = [_when(i["created_at"]) for i in linked if not i["pull"] and i.get("created_at")]
    induced = by_sha[inducing]["author_date"]
    date_ok = not reports or induced < min(reports)

    repo = REPOS / slug
    parent = by_sha[fix]["parents"][0]
    removed = deleted_lines(
        repo, parent, fix, row["paths"].split(";"), ignore_whitespace=True, skip_useless=True
    )
    ignore = (DATA / slug / _IGNORE_REVS_FILE).resolve()
    moved: Counter[str] = Counter()
    for path, lines in removed.items():
        moved += blame_lines(
            repo, parent, path, lines, ignore_whitespace=True, ignore_revs_file=ignore,
            detect_moves=True,
        )  # fmt: skip
    current = pl.read_parquet(DATA / slug / "szz.parquet").filter(
        (pl.col("fix_sha") == fix) & (pl.col("inducing_sha") == inducing)
    )
    return {
        "repo": slug,
        "correct": row["correct"] == "evet",
        "current": current.height > 0,
        "issue": bug,
        "linked": bool(linked),
        "moves": inducing in moved,
        "date": date_ok,
    }


VARIANTS: dict[str, tuple[str, ...]] = {
    "temel (etiketlenen eşlemeler)": (),
    "issue": ("issue",),
    "taşıma": ("moves",),
    "tarih": ("date",),
    "taşıma + tarih": ("moves", "date"),
    "issue + taşıma": ("issue", "moves"),
    "issue + tarih": ("issue", "date"),
    "issue + taşıma + tarih": ("issue", "moves", "date"),
}


def table(facts: list[dict[str, Any]]) -> list[str]:
    total_correct = sum(f["correct"] for f in facts)
    out = [
        "| Varyant | Kalan eşleme | Doğru | Doğruluk | Korunan doğru eşleme |",
        "| --- | --- | --- | --- | --- |",
    ]
    for name, keys in VARIANTS.items():
        kept = [f for f in facts if all(f[k] for k in keys)]
        good = sum(f["correct"] for f in kept)
        precision = f"%{100 * good / len(kept):.0f}" if kept else "—"
        out.append(f"| {name} | {len(kept)} | {good} | {precision} | {good}/{total_correct} |")
    return out


def volume(issues: Issues) -> list[str]:
    """D1 repolarında `issue` süzgecinin veri miktarına etkisi."""
    d1 = json.loads((DATA / "d1.json").read_text("utf-8"))["repos"]
    out = [
        "| Repo | Fix (SZZ'de eşlenen) | Bağlı issue/PR'ı olan | Hata etiketli | "
        "Hata getiren commit (şimdi → issue süzgeciyle) |",
        "| --- | --- | --- | --- | --- |",
    ]
    for repo in (r["repo"] for r in d1 if r.get("included", True)):
        szz = pl.read_parquet(DATA / repo / "szz.parquet")
        fixes = szz["fix_sha"].unique().to_list()
        messages = dict(
            pl.read_parquet(DATA / repo / "commits.parquet")
            .filter(pl.col("sha").is_in(fixes))
            .select("sha", "message")
            .iter_rows()
        )
        links = {sha: list(linked_issues(messages[sha])) for sha in fixes}
        info = issues(repo, sorted({n for ns in links.values() for n in ns}))
        bug_fixes = {
            sha
            for sha, ns in links.items()
            if any(
                info.get(n) and any(is_bug_label(lbl) for lbl in info[n]["labels"])  # type: ignore[index]
                for n in ns
            )
        }
        linked = sum(1 for ns in links.values() if any(info.get(n) for n in ns))
        before = szz["inducing_sha"].n_unique()
        after = szz.filter(pl.col("fix_sha").is_in(list(bug_fixes)))["inducing_sha"].n_unique()
        print(f"{repo}: {len(fixes)} fix, {len(bug_fixes)} hata etiketli", file=sys.stderr)
        out.append(f"| {repo} | {len(fixes)} | {linked} | {len(bug_fixes)} | {before} → {after} |")
    return out


def main() -> None:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("GITHUB_TOKEN gerekli (issue etiketleri ve tarihleri için)")
    issues = Issues(token)
    labels = {
        (r["fix_sha"], r["inducing_sha"]): r
        for r in csv.DictReader((LABELS / "szz-kontrol.csv").open(encoding="utf-8-sig"))
    }
    sample = list(csv.DictReader((LABELS / "szz-sample.csv").open(encoding="utf-8")))
    rows = []
    for s in sample:
        label = labels.get((s["fix_sha"], s["inducing_sha"]))
        if label is None or label["correct"] == "belirsiz":
            continue
        rows.append({**s, "correct": label["correct"]})
    facts = [pair_facts(r, issues) for r in rows]

    lines = [
        "# SZZ süzgeçleri: elle etiketli eşlemelerde ölçüm",
        "",
        "`eval/szz_variants.py` ile üretilir. Belirsizler hariç "
        f"{len(facts)} eşleme (#9). Doğruluk: kalan eşlemelerin elle doğru bulunanı.",
        "",
        *table(facts),
        "",
        f"Bağlı issue ya da PR'ı olan fix: {sum(f['linked'] for f in facts)}/{len(facts)}; "
        f"hata etiketli: {sum(f['issue'] for f in facts)}/{len(facts)}.",
    ]
    if "--hacim" in sys.argv:
        lines += ["", "## Veri miktarına etkisi (issue süzgeci, D1 repoları)", "", *volume(issues)]
    OUT.write_text("\n".join(lines) + "\n", "utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
