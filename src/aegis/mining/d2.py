"""D2 veri seti: LLM incelemesinin (RQ2) değerlendirildiği hatalı ve temiz commit'ler (#51).

D1'e alınan her repodan tabakalı örnekleme yapılır (`docs/presentation.md` §5.1):

- **Hatalı commit:** SZZ'nin bug-inducing dediği commit. Beklenen bulgular, bu hatayı sonradan
  düzelten fix'in sildiği satırların hatalı commit'teki yerleri (`blame_origins`); SZZ ile aynı
  süzgeçler (boşluk, yorum, import, docstring) uygulanır.
- **Temiz commit:** SZZ'nin hiç suçlamadığı ve en az `clean_min_age_days` yaşında olan commit
  (hata bulunmak için yeterince zaman geçmiş). Beklenen bulgu yoktur; her bulgu yanlış alarmdır.

İki sınıf, kaynak koduna eklenen satır sayısına göre aynı boyut dilimlerinden örneklenir; böylece
temiz commit'ler "küçük oldukları için temiz" olmaz. Her örnek, LLM'e verilecek diff'i de taşır:
deneyleri koşturmak için repo klonu ya da madencilik çıktısı gerekmez.

`after_cutoff`: commit tarihi, kullanılan LLM'in bilgi kesim tarihinden sonra mı (eğitim verisi
kirliliği alt kümesi, #55).
"""

import json
import random
import re
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import polars as pl

from aegis import __version__
from aegis.config import MiningConfig
from aegis.mining.szz import _IGNORE_REVS_FILE, blame_origins, deleted_lines

# Qwen2.5-Coder'ın yayımlanması (Eylül 2024); bilgi kesimi bundan önce.
DEFAULT_LLM_CUTOFF = date(2024, 9, 1)


@dataclass
class D2Sample:
    repo: str
    sha: str
    parent: str
    label: str  # "buggy" | "clean"
    date: str
    size_bin: int
    src_added: int
    files: list[str]
    diff: str
    expected: list[dict[str, Any]] = field(default_factory=list)  # [{"path", "line"}]
    fix_shas: list[str] = field(default_factory=list)
    after_cutoff: bool = False


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout


def expected_lines(
    repo: Path,
    data_dir: Path,
    inducing: str,
    szz: pl.DataFrame,
    commits: pl.DataFrame,
    config: MiningConfig,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Hatalı commit'te, sonradan düzeltilen satırlar ve onları düzelten fix'ler."""
    ma = config.szz_variant == "ma"
    ignore = (data_dir / _IGNORE_REVS_FILE).resolve() if ma else None
    if ignore is not None and not ignore.is_file():
        ignore = None
    parents = dict(commits.select("sha", "parents").iter_rows())
    found: set[tuple[str, int]] = set()
    fixes: list[str] = []
    pairs = szz.filter(pl.col("inducing_sha") == inducing)
    for fix in sorted(set(pairs["fix_sha"])):
        parent = parents[fix][0]
        paths = pairs.filter(pl.col("fix_sha") == fix)["path"].unique().to_list()
        removed = deleted_lines(repo, parent, fix, paths, ignore_whitespace=ma, skip_useless=ma)
        hit = False
        for path, lines in removed.items():
            for sha, orig_path, line in blame_origins(
                repo, parent, path, lines, ignore_whitespace=ma, ignore_revs_file=ignore
            ):
                if sha == inducing:
                    found.add((orig_path, line))
                    hit = True
        if hit:
            fixes.append(fix)
    expected = [{"path": p, "line": n} for p, n in sorted(found)]
    return expected, fixes


def _source_changes(files: pl.DataFrame, config: MiningConfig) -> pl.DataFrame:
    """Commit başına kaynak dosyaları (test değil) ve eklenen satır sayısı."""
    tests = [re.compile(p) for p in config.test_path_patterns]
    extensions = tuple(config.source_extensions)

    def is_source(path: str | None) -> bool:
        return (
            path is not None
            and path.endswith(extensions)
            and not any(t.search(path) for t in tests)
        )

    rows = [
        (sha, path, added)
        for sha, path, added, kind in files.select(
            "sha", "new_path", "lines_added", "change_type"
        ).iter_rows()
        if kind in ("ADD", "MODIFY", "RENAME") and is_source(path)
    ]
    frame = pl.DataFrame(
        rows, schema={"sha": pl.String(), "path": pl.String(), "added": pl.Int64()}, orient="row"
    )
    return frame.group_by("sha").agg(
        pl.col("path").sort().alias("paths"), pl.col("added").sum().alias("src_added")
    )


def sample_repo(
    repo: Path,
    data_dir: Path,
    d1: pl.DataFrame,
    *,
    per_label: int,
    bins: int = 3,
    min_added: int = 3,
    max_added: int = 300,
    clean_min_age_days: int = 365,
    llm_cutoff: date = DEFAULT_LLM_CUTOFF,
    seed: int = 0,
    config: MiningConfig | None = None,
) -> list[D2Sample]:
    """Bir repodan `per_label` hatalı ve `per_label` temiz commit (boyut dilimlerine göre)."""
    config = config or MiningConfig()
    rng = random.Random(f"{seed}:{data_dir.name}")
    commits = pl.read_parquet(data_dir / "commits.parquet")
    szz = pl.read_parquet(data_dir / "szz.parquet")
    changes = _source_changes(pl.read_parquet(data_dir / "files.parquet"), config)
    newest = d1["author_date"].max()
    candidates = (
        d1.select("sha", "author_date", "buggy")
        .join(changes, on="sha", how="inner")
        .filter(pl.col("src_added").is_between(min_added, max_added))
    )
    buggy = candidates.filter(pl.col("buggy"))
    clean = candidates.filter(
        ~pl.col("buggy") & (pl.col("author_date") <= newest - timedelta(days=clean_min_age_days))  # type: ignore[operator]
    )
    if buggy.is_empty() or clean.is_empty():
        return []
    # Boyut dilimleri hatalı commit'lerin dağılımından; iki sınıf aynı dilimlerden örneklenir.
    edges = [float(buggy["src_added"].quantile(i / bins, "nearest") or 0) for i in range(1, bins)]

    def size_bin(n: int) -> int:
        return sum(n > e for e in edges)

    parents = dict(commits.select("sha", "parents").iter_rows())
    quota = [per_label // bins + (1 if i < per_label % bins else 0) for i in range(bins)]
    samples: list[D2Sample] = []
    for label, pool in (("buggy", buggy), ("clean", clean)):
        by_bin: dict[int, list[dict[str, Any]]] = {}
        for row in pool.sort("sha").iter_rows(named=True):
            by_bin.setdefault(size_bin(row["src_added"]), []).append(row)
        for b in range(bins):
            rows = by_bin.get(b, [])
            rng.shuffle(rows)
            taken = 0
            for row in rows:
                if taken >= quota[b]:
                    break
                sha = row["sha"]
                parent = parents[sha][0] if parents.get(sha) else None
                if parent is None:
                    continue
                expected: list[dict[str, Any]] = []
                fixes: list[str] = []
                if label == "buggy":
                    expected, fixes = expected_lines(repo, data_dir, sha, szz, commits, config)
                    if not expected:  # beklenen satır bulunamadı (ör. dosya sonradan taşındı)
                        continue
                diff = _git(repo, "diff", "-U3", "--no-color", parent, sha, "--", *row["paths"])
                when: datetime = row["author_date"]
                samples.append(
                    D2Sample(
                        repo=data_dir.name,
                        sha=sha,
                        parent=parent,
                        label=label,
                        date=when.astimezone(UTC).isoformat(),
                        size_bin=b,
                        src_added=row["src_added"],
                        files=row["paths"],
                        diff=diff,
                        expected=expected,
                        fix_shas=fixes,
                        after_cutoff=when.date() > llm_cutoff,
                    )
                )
                taken += 1
    return samples


def build_d2(
    data_root: Path,
    clone_root: Path,
    out: Path,
    *,
    per_label: int = 50,
    seed: int = 0,
    llm_cutoff: date = DEFAULT_LLM_CUTOFF,
    bins: int = 3,
    min_added: int = 3,
    max_added: int = 300,
    clean_min_age_days: int = 365,
    config: MiningConfig | None = None,
) -> dict[str, Any]:
    """D1'e alınan her repodan D2 örnekleri; `out` (JSONL) ve yanına manifest (`.json`)."""
    manifest_d1 = json.loads((data_root / "d1.json").read_text("utf-8"))
    d1 = pl.read_parquet(data_root / "d1.parquet")
    included = [r["repo"] for r in manifest_d1["repos"] if r.get("included", True)]
    samples: list[D2Sample] = []
    for slug in included:
        samples += sample_repo(
            clone_root / slug,
            data_root / slug,
            d1.filter(pl.col("repo") == slug),
            per_label=per_label,
            bins=bins,
            min_added=min_added,
            max_added=max_added,
            clean_min_age_days=clean_min_age_days,
            seed=seed,
            llm_cutoff=llm_cutoff,
            config=config,
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as fh:
        for s in samples:
            fh.write(json.dumps(asdict(s), ensure_ascii=False) + "\n")
    counts: dict[str, dict[str, int]] = {}
    for s in samples:
        counts.setdefault(s.repo, {"buggy": 0, "clean": 0, "after_cutoff": 0})
        counts[s.repo][s.label] += 1
        counts[s.repo]["after_cutoff"] += s.after_cutoff
    manifest = {
        "aegis_version": __version__,
        "built_at": datetime.now(UTC).isoformat(),
        "seed": seed,
        "per_label": per_label,
        "bins": bins,
        "added_lines": [min_added, max_added],
        "clean_min_age_days": clean_min_age_days,
        "llm_cutoff": llm_cutoff.isoformat(),
        "samples": len(samples),
        "expected_lines": sum(len(s.expected) for s in samples),
        "repos": counts,
        "head_shas": {
            r["repo"]: r["head_sha"] for r in manifest_d1["repos"] if r["repo"] in included
        },
    }
    out.with_suffix(".json").write_text(json.dumps(manifest, indent=2), "utf-8")
    return manifest


def read_d2(path: Path) -> list[D2Sample]:
    with path.open(encoding="utf-8") as fh:
        return [D2Sample(**json.loads(line)) for line in fh if line.strip()]
