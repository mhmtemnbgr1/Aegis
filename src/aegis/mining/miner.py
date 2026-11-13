"""Commit geçmişinin PyDriller ile taranması (FR-01).

Çıktı, repo başına bir dizindir (`<data_dir>/<slug>/`):

- `commits.parquet`: commit başına bir satır, fix sınıflandırmasıyla birlikte
- `files.parquet`: commit × değişen dosya
- `functions.parquet`: commit × değişen Python fonksiyonu
- `meta.json`: veri sürümü (NFR-04)

Şemalar `aegis.mining.schema` ve docs/mining-schema.md içinde.
"""

import json
import logging
import re
import subprocess
import time
from collections.abc import Callable, Collection, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl
from pydriller import Repository

from aegis import __version__
from aegis.config import MiningConfig
from aegis.mining import schema
from aegis.mining.fixes import FixClassifier, linked_issues

logger = logging.getLogger(__name__)

LabelSource = Callable[[Collection[int]], Mapping[int, Collection[str]]]
"""Issue numaraları → etiketler. Verilmezse yalnızca mesaj kalıpları kullanılır."""

_SCP_URL = re.compile(r"^[\w.-]+@([\w.-]+):(.+)$")


@dataclass(frozen=True)
class MineResult:
    slug: str
    out_dir: str
    head_sha: str
    commits: int
    merges: int
    fixes: int
    files: int
    functions: int
    function_errors: int
    duration_seconds: float


def is_remote(spec: str) -> bool:
    return "://" in spec or _SCP_URL.match(spec) is not None


def slug_from_url(url: str) -> str:
    """`https://github.com/httpie/cli.git` → `httpie__cli`."""
    if m := _SCP_URL.match(url):
        path = m.group(2)
    else:
        path = url.split("://", 1)[-1].split("/", 1)[-1] if "://" in url else url
    parts = [p for p in path.rstrip("/").removesuffix(".git").split("/") if p]
    return "__".join(parts[-2:]) if parts else "repo"


def github_repository(url: str) -> str | None:
    """GitHub URL'si ise `owner/name`, değilse None."""
    if "github.com" not in url:
        return None
    return slug_from_url(url).replace("__", "/", 1)


def remote_url(repo: Path) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(repo), "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def repo_slug(repo: Path) -> str:
    url = remote_url(repo)
    return slug_from_url(url) if url else repo.resolve().name


def ensure_clone(url: str, clone_root: Path) -> Path:
    """Repoyu `clone_root/<slug>` altına tam geçmişle klonlar; zaten varsa olduğu gibi kullanır."""
    dest = clone_root / slug_from_url(url)
    if (dest / ".git").exists():
        logger.info("mevcut klon kullanılıyor: %s", dest)
        return dest
    clone_root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", "--quiet", url, str(dest)], check=True, capture_output=True)
    return dest


def count_commits(repo: Path, since: datetime | None = None) -> int:
    args = ["git", "-C", str(repo), "rev-list", "--count", "HEAD"]
    if since is not None:
        args.insert(-1, f"--since={since.isoformat()}")
    out = subprocess.run(args, check=True, capture_output=True, text=True).stdout
    return int(out.strip())


def _head_sha(repo: Path) -> str:
    args = ["git", "-C", str(repo), "rev-parse", "HEAD"]
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout.strip()


def _posix(path: str | None) -> str | None:
    return path.replace("\\", "/") if path is not None else None


def mine_repository(
    repo: Path,
    out_dir: Path,
    config: MiningConfig | None = None,
    *,
    slug: str | None = None,
    since: datetime | None = None,
    functions: bool = True,
    label_source: LabelSource | None = None,
    on_commit: Callable[[], None] | None = None,
) -> MineResult:
    """`repo`'nun HEAD'inden erişilen commit'leri (eskiden yeniye) tarar ve `out_dir`'e yazar."""
    config = config or MiningConfig()
    slug = slug or repo_slug(repo)
    started = time.perf_counter()
    commits: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    funcs: list[dict[str, Any]] = []
    function_errors = 0

    for c in Repository(str(repo), since=since).traverse_commits():
        added = deleted = 0
        modified = c.modified_files  # merge commit'lerinde PyDriller boş liste döner
        for mf in modified:
            path = _posix(mf.new_path or mf.old_path) or ""
            is_python = path.endswith(".py")
            added += mf.added_lines
            deleted += mf.deleted_lines
            files.append(
                {
                    "repo": slug,
                    "sha": c.hash,
                    "old_path": _posix(mf.old_path),
                    "new_path": _posix(mf.new_path),
                    "change_type": mf.change_type.name,
                    "lines_added": mf.added_lines,
                    "lines_deleted": mf.deleted_lines,
                    "is_python": is_python,
                }
            )
            if functions and is_python:
                try:
                    methods = mf.changed_methods
                except Exception as exc:  # lizard ayrıştıramadığında
                    function_errors += 1
                    logger.debug("fonksiyonlar çıkarılamadı %s %s: %s", c.hash, path, exc)
                    continue
                funcs.extend(
                    {
                        "repo": slug,
                        "sha": c.hash,
                        "path": path,
                        "name": m.name,
                        "long_name": m.long_name,
                        "start_line": m.start_line,
                        "end_line": m.end_line,
                        "nloc": m.nloc,
                        "complexity": m.complexity,
                    }
                    for m in methods
                )
        commits.append(
            {
                "repo": slug,
                "sha": c.hash,
                "parents": list(c.parents),
                "is_merge": c.merge,
                "author_name": c.author.name,
                "author_email": c.author.email,
                "author_date": c.author_date.astimezone(UTC),
                # GitPython: UTC'nin batısındaki saniye; işaret çevrilerek dakikaya dönüştürülür.
                "author_utc_offset_minutes": -c.author_timezone // 60,
                "committer_date": c.committer_date.astimezone(UTC),
                "message": c.msg,
                "files_changed": len(modified),
                "lines_added": added,
                "lines_deleted": deleted,
            }
        )
        if on_commit is not None:
            on_commit()

    _classify(commits, config, label_source)

    out_dir.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(commits, schema=schema.COMMITS).write_parquet(out_dir / "commits.parquet")
    pl.DataFrame(files, schema=schema.FILES).write_parquet(out_dir / "files.parquet")
    pl.DataFrame(funcs, schema=schema.FUNCTIONS).write_parquet(out_dir / "functions.parquet")

    result = MineResult(
        slug=slug,
        out_dir=str(out_dir),
        head_sha=_head_sha(repo),
        commits=len(commits),
        merges=sum(1 for c in commits if c["is_merge"]),
        fixes=sum(1 for c in commits if c["is_fix"]),
        files=len(files),
        functions=len(funcs),
        function_errors=function_errors,
        duration_seconds=round(time.perf_counter() - started, 2),
    )
    meta = {
        "schema_version": schema.SCHEMA_VERSION,
        "aegis_version": __version__,
        "mined_at": datetime.now(UTC).isoformat(),
        "remote_url": remote_url(repo),
        "since": since.isoformat() if since else None,
        "functions": functions,
        "issue_labels": label_source is not None,
        "mining_config": config.model_dump(mode="json", exclude={"data_dir", "clone_dir"}),
        **asdict(result),
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), "utf-8")
    return result


def _classify(
    commits: list[dict[str, Any]], config: MiningConfig, label_source: LabelSource | None
) -> None:
    labels: Mapping[int, Collection[str]] = {}
    if label_source is not None:
        wanted = {n for c in commits if not c["is_merge"] for n in linked_issues(c["message"])}
        labels = label_source(sorted(wanted)) if wanted else {}
    classifier = FixClassifier(config)
    for c in commits:
        fix = classifier.classify(c["message"], is_merge=c["is_merge"], issue_labels=labels)
        c["is_fix"] = fix.is_fix
        c["fix_signals"] = list(fix.signals)
        c["linked_issues"] = list(fix.linked_issues)


def reclassify(out_dir: Path, config: MiningConfig | None = None) -> tuple[int, int]:
    """Mevcut tarama çıktısında fix kararlarını güncel sınıflandırıcıyla yeniden verir.

    Fix kalıpları değiştiğinde (ör. #8 sonrası) yeniden tarama gerekmez: `commits.parquet`'teki
    `is_fix`/`fix_signals` ve `kamei.parquet`'teki FIX metriği güncellenir. Bağlı issue
    etiketinden gelen kararlar (`label:` sinyali) korunur. (önceki, yeni) fix sayısını döndürür.
    """
    config = config or MiningConfig()
    path = out_dir / "commits.parquet"
    commits = pl.read_parquet(path)
    classifier = FixClassifier(config)
    is_fix: list[bool] = []
    signals: list[list[str]] = []
    for message, merge, old in commits.select("message", "is_merge", "fix_signals").iter_rows():
        fix = classifier.classify(message, is_merge=merge)
        labelled = [s for s in (old or []) if s.startswith("label:")]
        is_fix.append(fix.is_fix or bool(labelled))
        signals.append([*fix.signals, *labelled])
    before = int(commits["is_fix"].sum())
    commits = commits.with_columns(
        pl.Series("is_fix", is_fix), pl.Series("fix_signals", signals, dtype=pl.List(pl.String()))
    )
    commits.write_parquet(path)
    kamei_path = out_dir / "kamei.parquet"
    if kamei_path.is_file():
        flags = commits.select("sha", pl.col("is_fix").cast(pl.Float64).alias("_fix"))
        kamei = pl.read_parquet(kamei_path).join(flags, on="sha", how="left")
        kamei.with_columns(pl.col("_fix").fill_null(pl.col("fix")).alias("fix")).drop(
            "_fix"
        ).write_parquet(kamei_path)
    return before, sum(is_fix)
