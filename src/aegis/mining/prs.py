"""PR düzeyinde D1: commit → PR eşlemesi, PR etiketi ve özellikleri (FR-11, #73).

Eşleme GitHub API'si olmadan, yalnızca git geçmişinden yapılır (`main`'in ilk ebeveyn hattı):

- **merge:** "Merge pull request #N" mesajlı merge commit'i. PR'ın commit'leri
  `git rev-list --no-merges <ebeveyn1>..<ebeveyn2>`; diff, merge-base ile PR başı arasındaki
  birleşik diff'tir.
- **squash:** Başlığı "(#N)" ile biten tek ebeveynli commit. PR tek commit'tir; özellikleri
  commit düzeyindeki D1 satırıyla aynıdır. Rebase ile birleştirilen PR'lar git'ten ayırt
  edilemez ve dışarıda kalır.

**Etiket:** PR'ın commit'lerinden en az biri SZZ'ye göre bug-inducing ise hatalı; `fixed_at`,
bu commit'lerin hatalarının ilk düzeltildiği an.

**Özellikler:** 14 Kamei metriği PR'ın birleşik diff'i üzerinden, `n_commits` ve `n_authors`
eklenerek. Yalnızca PR açıldığında ya da güncellendiğinde bilinen bilgiler kullanılır:
geçmişe dayalı metrikler PR'ın **ilk** commit'inin zamanında (`as_of`) hesaplanır, böylece
PR'ın kendi commit'leri ve sonrası görünmez. Merge zamanı, PR süresi, review ya da yorum
sayısı gibi sonradan oluşan bilgiler hiç okunmaz (`FORBIDDEN`).
"""

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import polars as pl

from aegis.config import AegisConfig
from aegis.features.extra import EXTRA, extra_metrics
from aegis.features.history import Change, ChangeHistory, developer_id
from aegis.features.kamei import KAMEI, kamei_metrics
from aegis.mining.gitfiles import git, tree_changes

PR_FEATURES: tuple[str, ...] = (*KAMEI, *EXTRA, "n_commits", "n_authors")
FORBIDDEN = frozenset(
    {
        "merged_at",
        "closed_at",
        "duration",
        "time_to_merge",
        "reviews",
        "review_comments",
        "comments",
        "approvals",
        "changes_requested",
    }
)
"""PR açıldığı anda bilinmeyen, bu yüzden özellik olarak kullanılamayacak bilgiler."""

_MERGE = re.compile(r"^Merge pull request #(\d+)\b")
_SQUASH = re.compile(r"\(#(\d+)\)\s*$")
_SEP = "\x1f"


@dataclass(frozen=True)
class PullRequest:
    number: int
    style: Literal["merge", "squash"]
    sha: str
    """PR'ı main'e getiren commit (merge ya da squash commit'i)."""
    commits: tuple[str, ...]
    """PR'ın merge olmayan commit'leri, eskiden yeniye."""
    base: str
    """Birleşik diff'in tabanı: merge-base (merge) ya da ebeveyn (squash)."""
    head: str


def find_prs(repo: Path, ref: str = "HEAD") -> list[PullRequest]:
    """`ref`'in ilk ebeveyn hattındaki PR'lar, eskiden yeniye."""
    out: list[PullRequest] = []
    log = git(repo, "log", "--first-parent", "--reverse", f"--format=%H{_SEP}%P{_SEP}%s", ref)
    for line in log.splitlines():
        sha, parents, subject = line.split(_SEP, 2)
        ps = parents.split()
        if len(ps) == 2 and (m := _MERGE.match(subject)):
            members = git(repo, "rev-list", "--no-merges", "--reverse", f"{ps[0]}..{ps[1]}")
            if members.strip():
                base = git(repo, "merge-base", ps[0], ps[1]).strip()
                out.append(
                    PullRequest(int(m.group(1)), "merge", sha, tuple(members.split()), base, ps[1])
                )
        elif len(ps) == 1 and (m := _SQUASH.search(subject)):
            out.append(PullRequest(int(m.group(1)), "squash", sha, (sha,), ps[0], sha))
    return out


def pr_features(
    change: Change,
    history: ChangeHistory,
    *,
    as_of: datetime,
    n_commits: int,
    n_authors: int,
    config: AegisConfig | None = None,
) -> dict[str, float]:
    """Bir PR'ın özellikleri: yalnızca değişiklik, `as_of` öncesi geçmiş ve PR'ın commit'leri."""
    return {
        **kamei_metrics(change, history, as_of=as_of),
        **extra_metrics(
            change,
            risky=(config or AegisConfig()).gatekeeper.heuristic.risky_paths,
            test_patterns=(config or AegisConfig()).mining.test_path_patterns,
        ),
        "n_commits": float(n_commits),
        "n_authors": float(n_authors),
    }


def build_pr_rows(repo: Path, data_dir: Path, d1: pl.DataFrame) -> pl.DataFrame:
    """Bir reponun PR satırları. `d1`: bu reponun commit düzeyindeki D1 satırları."""
    commits = pl.read_parquet(data_dir / "commits.parquet")
    info: dict[str, tuple[datetime, str, bool]] = {
        sha: (time, developer_id(name, email), bool(fix))
        for sha, time, name, email, fix in commits.select(
            "sha", "committer_date", "author_name", "author_email", "is_fix"
        ).iter_rows()
    }
    by_sha = {row["sha"]: row for row in d1.iter_rows(named=True)}
    slug = d1["repo"][0] if d1.height else data_dir.name
    history: ChangeHistory | None = None
    rows: list[dict[str, Any]] = []
    for pr in find_prs(repo):
        members = [by_sha[s] for s in pr.commits if s in by_sha]
        known = [s for s in pr.commits if s in info]
        if not members or not known:
            continue
        authors = {info[s][1] for s in known}
        if pr.style == "squash":
            row = by_sha[pr.sha]
            as_of = row["as_of"]
            features = {k: row[k] for k in (*KAMEI, *EXTRA)} | {
                "n_commits": 1.0,
                "n_authors": 1.0,
            }
        else:
            if history is None:
                history = ChangeHistory.from_frames(
                    commits, pl.read_parquet(data_dir / "files.parquet")
                )
            as_of = min(info[s][0] for s in known)
            change = Change(
                developer=info[known[-1]][1],
                files=tree_changes(repo, pr.base, pr.head),
                is_fix=any(info[s][2] for s in known),
            )
            features = pr_features(
                change, history, as_of=as_of, n_commits=len(known), n_authors=len(authors)
            )
        fixed = [m["fixed_at"] for m in members if m["buggy"]]
        rows.append(
            {
                "repo": slug,
                "sha": pr.sha,
                "pr": pr.number,
                "style": pr.style,
                "as_of": as_of,
                **features,
                "buggy": bool(fixed),
                "fixed_at": min(fixed) if fixed else None,
                "commits": [m["sha"] for m in members],
            }
        )
    schema = {
        "repo": pl.String(),
        "sha": pl.String(),
        "pr": pl.Int64(),
        "style": pl.String(),
        "as_of": pl.Datetime("us", "UTC"),
        **{f: pl.Float64() for f in PR_FEATURES},
        "buggy": pl.Boolean(),
        "fixed_at": pl.Datetime("us", "UTC"),
        "commits": pl.List(pl.String()),
    }
    return pl.DataFrame(rows, schema=schema).sort("as_of", maintain_order=True)


def build_d1_pr(
    data_root: Path, clone_root: Path, d1_path: Path, out: Path
) -> list[dict[str, Any]]:
    """Tüm repoların PR satırlarını `out`'a yazar; repo başına özet döndürür."""
    d1 = pl.read_parquet(d1_path)
    frames: list[pl.DataFrame] = []
    stats: list[dict[str, Any]] = []
    for slug in sorted(set(d1["repo"])):
        repo = clone_root / slug
        if not (repo / ".git").exists():
            continue
        rows = build_pr_rows(repo, data_root / slug, d1.filter(pl.col("repo") == slug))
        frames.append(rows)
        merge = int((rows["style"] == "merge").sum())
        positives = int(rows["buggy"].sum())
        stats.append(
            {
                "repo": slug,
                "prs": rows.height,
                "merge": merge,
                "squash": rows.height - merge,
                "style": "merge" if merge > rows.height / 2 else "squash",
                "positives": positives,
                "positive_rate": round(positives / rows.height, 4) if rows.height else 0.0,
            }
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    if frames:
        pl.concat(frames).write_parquet(out)
    return stats
