"""D1: commit düzeyinde JIT hata tahmini veri seti (#13).

Her repo için madencilik çıktıları birleştirilir:

- satırlar: SZZ penceresindeki (son `history_years` yıl), merge olmayan ve en az bir dosya
  değiştiren commit'ler,
- özellikler: `kamei.parquet` (14 metrik, `as_of` = commit zamanı),
- etiket: `buggy` = commit, SZZ'nin bulduğu bir bug-inducing commit mi; `fixed_at` bu hatanın
  ilk düzeltildiği an (etiketin bilindiği zaman, temiz commit'lerde boş).

Bilinen sınırlama: pencerenin sonuna yakın commit'lerin hataları henüz bulunmamış olabilir
(etiket gecikmesi); zaman sıralı bölmede tampon ile ele alınır (#14).
"""

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from aegis import __version__
from aegis.features.kamei import KAMEI
from aegis.mining import schema

MIN_POSITIVES = 200
"""Bir reponun D1'de kullanılabilmesi için gereken en az bug-inducing commit sayısı."""


@dataclass(frozen=True)
class RepoStats:
    repo: str
    head_sha: str
    szz_variant: str
    cutoff: str
    commits: int
    fixes: int
    positives: int
    positive_rate: float
    enough: bool


def build_repo(data_dir: Path) -> tuple[pl.DataFrame, RepoStats]:
    """Tek bir reponun D1 satırları ve özet sayıları."""
    commits = pl.read_parquet(data_dir / "commits.parquet")
    kamei = pl.read_parquet(data_dir / "kamei.parquet")
    szz = pl.read_parquet(data_dir / "szz.parquet")
    meta = json.loads((data_dir / "meta.json").read_text("utf-8"))
    szz_meta = json.loads((data_dir / "szz_meta.json").read_text("utf-8"))
    cutoff = datetime.fromisoformat(szz_meta["cutoff"])

    # Her inducing commit'in ilk düzeltildiği an: etiketin "bilindiği" zaman (#14).
    fixed = szz.group_by("inducing_sha").agg(pl.col("fix_date").min().alias("fixed_at"))
    rows = (
        kamei.join(commits.select("sha", "author_date", "files_changed"), on="sha", how="inner")
        .filter((pl.col("author_date") >= cutoff) & (pl.col("files_changed") > 0))
        .join(fixed, left_on="sha", right_on="inducing_sha", how="left")
        .with_columns(pl.col("fixed_at").is_not_null().alias("buggy"))
        .select("repo", "sha", "author_date", "as_of", *KAMEI, "buggy", "fixed_at")
        .sort("as_of", maintain_order=True)
    )
    positives = int(rows["buggy"].sum())
    stats = RepoStats(
        repo=meta["slug"],
        head_sha=meta["head_sha"],
        szz_variant=szz_meta["variant"],
        cutoff=cutoff.isoformat(),
        commits=rows.height,
        fixes=int(rows["fix"].sum()),
        positives=positives,
        positive_rate=round(positives / rows.height, 4) if rows.height else 0.0,
        enough=positives >= MIN_POSITIVES,
    )
    return rows, stats


def build_d1(data_root: Path, out: Path) -> list[RepoStats]:
    """`data_root` altındaki tüm repoları birleştirip `out` (Parquet) ve yanına manifest yazar.

    Yalnızca kamei ve SZZ çıktısı olan repo dizinleri alınır.
    """
    frames: list[pl.DataFrame] = []
    stats: list[RepoStats] = []
    for repo_dir in sorted(p for p in data_root.iterdir() if p.is_dir()):
        if not all((repo_dir / f).is_file() for f in ("kamei.parquet", "szz.parquet")):
            continue
        rows, repo_stats = build_repo(repo_dir)
        frames.append(rows)
        stats.append(repo_stats)
    out.parent.mkdir(parents=True, exist_ok=True)
    data = pl.concat(frames) if frames else pl.DataFrame(schema=_d1_schema())
    data.write_parquet(out)
    manifest: dict[str, Any] = {
        "schema_version": schema.SCHEMA_VERSION,
        "aegis_version": __version__,
        "built_at": datetime.now(UTC).isoformat(),
        "min_positives": MIN_POSITIVES,
        "rows": data.height,
        "repos": [asdict(s) for s in stats],
    }
    out.with_suffix(".json").write_text(json.dumps(manifest, indent=2), "utf-8")
    return stats


def _d1_schema() -> dict[str, pl.DataType]:
    return {
        "repo": pl.String(),
        "sha": pl.String(),
        "author_date": schema.UTC_TS,
        "as_of": schema.UTC_TS,
        **{name: pl.Float64() for name in KAMEI},
        "buggy": pl.Boolean(),
        "fixed_at": schema.UTC_TS,
    }
