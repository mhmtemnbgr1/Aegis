"""SZZ: fix commit'lerinden hatayı getiren (bug-inducing) commit'lere eşleme (FR-03).

pyszz PyPI'da olmadığından SZZ doğrudan `git diff` ve `git blame` üzerine kuruludur:

1. Son `history_years` yıldaki (varsayılan: tüm geçmiş), merge olmayan ve
   `max_files_per_commit`'ten küçük fix'ler alınır.
2. Her fix'te değişen kaynak dosyalarının (test dosyaları hariç) silinen ya da değiştirilen
   satırları `git diff -U0 <ebeveyn> <fix>` ile bulunur.
3. Bu satırlar ebeveyn commit'te `git blame` ile son değiştiren commit'e izlenir.
4. Fix'ten sonra yazılmış, merge olan ya da yok sayılan aday commit'ler elenir.

Varyantlar:

- `b` (B-SZZ): düz diff ve düz blame.
- `ma` (MA-SZZ'ye yakın): diff ve blame boşluk değişikliklerini yok sayar (`-w`); boş, yalnız
  yorum olan, import ve docstring satırları blame edilmez; merge commit'leri ve
  `max_files_per_commit`'i aşan toplu değişiklikler (biçimlendirme, taşıma, lisans başlığı vb.)
  `--ignore-revs-file` ile atlanır.

Çıktı `szz.parquet` (fix × inducing × dosya) ve `szz_meta.json`'dur.
"""

import ast
import json
import re
import subprocess
import time
import warnings
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import polars as pl
from unidiff.patch import PatchSet

from aegis import __version__
from aegis.config import MiningConfig
from aegis.mining import schema

_BLAME_HEADER = re.compile(r"^([0-9a-f]{40}) \d+ (\d+)(?: \d+)?$")
_IGNORE_REVS_FILE = ".szz-ignore-revs"


@dataclass(frozen=True)
class SzzResult:
    variant: str
    cutoff: str
    fixes_in_window: int
    fixes_skipped_large: int
    fixes_without_source: int
    fixes_with_inducing: int
    inducing_commits: int
    pairs: int
    duration_seconds: float


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout


_IMPORT = re.compile(r"^(import\s+\w|from\s+[\w.]+\s+import(\s|\(|$))")


def _is_useless(line: str) -> bool:
    """Boş, yalnız yorum ya da import satırı.

    Import satırları hatalı mantık taşımaz; fix'ler çoğu zaman yan etki olarak import'ları da
    düzenler ve SZZ bu satırları yazan ilgisiz commit'i suçlar (#9 elle kontrolünde görüldü).
    """
    stripped = line.strip()
    return not stripped or stripped.startswith("#") or bool(_IMPORT.match(stripped))


def docstring_lines(source: str) -> set[int]:
    """Modül, sınıf ve fonksiyon docstring'lerinin satır numaraları (1 tabanlı).

    Ayrıştırılamayan kaynakta (ör. Python 2 sözdizimi) boş küme döner.
    """
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # eski kaynaklardaki geçersiz kaçış uyarıları
            tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return set()
    lines: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        first = node.body[0] if node.body else None
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            lines.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    return lines


def deleted_lines(
    repo: Path,
    parent: str,
    fix: str,
    paths: Iterable[str],
    *,
    ignore_whitespace: bool,
    skip_useless: bool,
) -> dict[str, list[int]]:
    """Ebeveyndeki yol → fix'in sildiği/değiştirdiği satır numaraları (ebeveyndeki numaralar)."""
    wanted = set(paths)
    args = ["diff", "-U0", "--no-color", "--no-ext-diff", "-M"]
    if ignore_whitespace:
        args.append("-w")
    patch = PatchSet(_git(repo, *args, parent, fix))
    result: dict[str, list[int]] = {}
    for pf in patch:
        source = pf.source_file.removeprefix("a/")
        if source not in wanted:
            continue
        docstrings: set[int] = set()
        if skip_useless and source.endswith(".py"):
            docstrings = docstring_lines(_git(repo, "show", f"{parent}:{source}"))
        lines = [
            line.source_line_no
            for hunk in pf
            for line in hunk
            if line.is_removed
            and line.source_line_no is not None
            and not (
                skip_useless and (_is_useless(line.value) or line.source_line_no in docstrings)
            )
        ]
        if lines:
            result[source] = lines
    return result


def _ranges(lines: list[int]) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for n in sorted(set(lines)):
        if ranges and n == ranges[-1][1] + 1:
            ranges[-1] = (ranges[-1][0], n)
        else:
            ranges.append((n, n))
    return ranges


def blame_lines(
    repo: Path,
    rev: str,
    path: str,
    lines: list[int],
    *,
    ignore_whitespace: bool,
    ignore_revs_file: Path | None = None,
    detect_moves: bool = False,
) -> Counter[str]:
    """`rev`'deki `path`'in verilen satırlarını son değiştiren commit'ler → satır sayısı.

    `detect_moves`: dosya içinde ve dosyalar arasında taşınan/kopyalanan satırlar (`-M -C`) asıl
    yazıldıkları commit'e izlenir; taşıma commit'i suçlanmaz.
    """
    args = ["blame", "--porcelain"]
    if ignore_whitespace:
        args.append("-w")
    if detect_moves:
        args += ["-M", "-C"]
    if ignore_revs_file is not None:
        args += ["--ignore-revs-file", str(ignore_revs_file)]
    for start, end in _ranges(lines):
        args += ["-L", f"{start},{end}"]
    counts: Counter[str] = Counter()
    for line in _git(repo, *args, rev, "--", path).splitlines():
        if m := _BLAME_HEADER.match(line):
            counts[m.group(1)] += 1
    return counts


_LINE_HEADER = re.compile(r"^([0-9a-f]{40}) (\d+) \d+(?: \d+)?$")


def blame_origins(
    repo: Path,
    rev: str,
    path: str,
    lines: list[int],
    *,
    ignore_whitespace: bool,
    ignore_revs_file: Path | None = None,
) -> list[tuple[str, str, int]]:
    """Satırların kaynağı: (son değiştiren commit, o commit'teki dosya yolu, o commit'teki satır).

    D2'nin beklenen bulguları için (#51): bir fix'in sildiği satırların, hatayı getiren commit'te
    hangi dosyanın hangi satırı olduğu. `blame_lines` ile aynı ayarlar kullanılmalıdır.
    """
    args = ["blame", "--line-porcelain"]
    if ignore_whitespace:
        args.append("-w")
    if ignore_revs_file is not None:
        args += ["--ignore-revs-file", str(ignore_revs_file)]
    for start, end in _ranges(lines):
        args += ["-L", f"{start},{end}"]
    origins: list[tuple[str, str, int]] = []
    sha, line_no = "", 0
    for line in _git(repo, *args, rev, "--", path).splitlines():
        if m := _LINE_HEADER.match(line):
            sha, line_no = m.group(1), int(m.group(2))
        elif line.startswith("filename ") and sha:
            origins.append((sha, line.removeprefix("filename "), line_no))
            sha = ""
    return origins


def run_szz(
    repo: Path,
    data_dir: Path,
    config: MiningConfig | None = None,
    *,
    incremental_from: str | None = None,
    on_start: Callable[[int], None] | None = None,
    on_fix: Callable[[], None] | None = None,
) -> SzzResult:
    """`data_dir`'deki `commits.parquet` ve `files.parquet`'ten SZZ eşlemelerini üretir."""
    config = config or MiningConfig()
    started = time.perf_counter()
    commits = pl.read_parquet(data_dir / "commits.parquet")
    files = pl.read_parquet(data_dir / "files.parquet")
    ma = config.szz_variant == "ma"
    slug = commits["repo"][0] if commits.height else data_dir.name

    latest: datetime = commits["author_date"].max() if commits.height else datetime.now(UTC)  # type: ignore[assignment]
    if config.history_years is None:
        earliest: datetime = commits["author_date"].min() if commits.height else latest  # type: ignore[assignment]
        cutoff = earliest
    else:
        cutoff = latest - timedelta(days=round(365.25 * config.history_years))
    in_window = commits.filter(
        pl.col("is_fix") & ~pl.col("is_merge") & (pl.col("author_date") >= cutoff)
    )
    large = in_window.filter(pl.col("files_changed") > config.max_files_per_commit)
    fixes = in_window.filter(pl.col("files_changed") <= config.max_files_per_commit)

    current_head = json.loads((data_dir / "meta.json").read_text("utf-8")).get("last_processed_sha")
    previous_pairs: pl.DataFrame | None = None
    if incremental_from is not None and (data_dir / "szz_meta.json").is_file():
        old_meta = json.loads((data_dir / "szz_meta.json").read_text("utf-8"))
        old_head = old_meta.get("head_sha")
        settings_match = all(
            old_meta.get(key) == value
            for key, value in {
                "variant": config.szz_variant,
                "history_years": config.history_years,
                "max_files_per_commit": config.max_files_per_commit,
                "source_extensions": config.source_extensions,
                "test_path_patterns": config.test_path_patterns,
            }.items()
        )
        ancestor = (
            subprocess.run(
                ["git", "-C", str(repo), "merge-base", "--is-ancestor", old_head, current_head],
                capture_output=True,
            ).returncode
            == 0
            if old_head and current_head
            else False
        )
        if settings_match and ancestor and (data_dir / "szz.parquet").is_file():
            if old_head == current_head:
                new_shas: set[str] = set()
            else:
                out = subprocess.run(
                    ["git", "-C", str(repo), "rev-list", f"{old_head}..{current_head}"],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout
                new_shas = set(out.splitlines())
            fixes_to_process = fixes.filter(pl.col("sha").is_in(new_shas))
            previous_pairs = pl.read_parquet(data_dir / "szz.parquet").filter(
                pl.col("fix_date") >= cutoff
            )
        else:
            fixes_to_process = fixes
    else:
        fixes_to_process = fixes

    merges = set(commits.filter(pl.col("is_merge"))["sha"])
    dates = dict(zip(commits["sha"], commits["author_date"], strict=True))
    ignored: set[str] = set()
    ignore_file: Path | None = None
    if ma:
        ignored = set(commits.filter(pl.col("files_changed") > config.max_files_per_commit)["sha"])
        ignore_file = (data_dir / _IGNORE_REVS_FILE).resolve()
        ignore_file.write_text("".join(f"{sha}\n" for sha in sorted(ignored)), "utf-8")

    tests = [re.compile(p) for p in config.test_path_patterns]
    extensions = tuple(config.source_extensions)

    def is_source(path: str | None) -> bool:
        return (
            path is not None
            and path.endswith(extensions)
            and not any(t.search(path) for t in tests)
        )

    source_files = files.filter(
        pl.col("change_type").is_in(["MODIFY", "RENAME"])
        & pl.col("sha").is_in(fixes_to_process["sha"].implode())
    )
    paths_by_fix: dict[str, list[str]] = {}
    for sha, old_path in source_files.select("sha", "old_path").iter_rows():
        if is_source(old_path):
            paths_by_fix.setdefault(sha, []).append(old_path)

    if on_start is not None:
        on_start(fixes_to_process.height)
    rows: list[dict[str, Any]] = []
    without_source = 0
    for fix in fixes_to_process.select("sha", "parents", "author_date").iter_rows(named=True):
        paths = paths_by_fix.get(fix["sha"])
        if not paths or not fix["parents"]:
            without_source += 1
            if on_fix is not None:
                on_fix()
            continue
        parent = fix["parents"][0]
        removed = deleted_lines(
            repo, parent, fix["sha"], paths, ignore_whitespace=ma, skip_useless=ma
        )
        for path, lines in removed.items():
            counts = blame_lines(
                repo, parent, path, lines, ignore_whitespace=ma, ignore_revs_file=ignore_file
            )
            for sha, n in counts.items():
                induced_at = dates.get(sha)
                if (
                    sha in merges
                    or sha in ignored
                    or induced_at is None  # taranan geçmişin dışında (ör. --since)
                    or induced_at > fix["author_date"]
                ):
                    continue
                rows.append(
                    {
                        "repo": slug,
                        "fix_sha": fix["sha"],
                        "inducing_sha": sha,
                        "path": path,
                        "blamed_lines": n,
                        "fix_date": fix["author_date"],
                        "inducing_date": induced_at,
                    }
                )
        if on_fix is not None:
            on_fix()

    new_pairs = pl.DataFrame(rows, schema=schema.SZZ)
    pairs = (
        pl.concat([previous_pairs, new_pairs], how="vertical")
        if previous_pairs is not None
        else new_pairs
    )
    pairs.write_parquet(data_dir / "szz.parquet")
    result = SzzResult(
        variant=config.szz_variant,
        cutoff=cutoff.isoformat(),
        fixes_in_window=in_window.height,
        fixes_skipped_large=large.height,
        fixes_without_source=without_source,
        fixes_with_inducing=pairs["fix_sha"].n_unique(),
        inducing_commits=pairs["inducing_sha"].n_unique(),
        pairs=pairs.select("fix_sha", "inducing_sha").unique().height,
        duration_seconds=round(time.perf_counter() - started, 2),
    )
    meta = {
        "schema_version": schema.SCHEMA_VERSION,
        "aegis_version": __version__,
        "computed_at": datetime.now(UTC).isoformat(),
        "head_sha": current_head or (commits["sha"][-1] if commits.height else None),
        "history_years": config.history_years,
        "max_files_per_commit": config.max_files_per_commit,
        "source_extensions": config.source_extensions,
        "test_path_patterns": config.test_path_patterns,
        "ignored_revs": len(ignored),
        **asdict(result),
    }
    (data_dir / "szz_meta.json").write_text(json.dumps(meta, indent=2), "utf-8")
    return result


def review_sample(data_dir: Path, n: int = 50, seed: int = 0) -> pl.DataFrame:
    """Elle kontrol için rastgele `n` fix → inducing eşlemesi (#9).

    `correct` sütunu boş bırakılır; kontrol eden kişi `evet`, `hayir` veya `belirsiz` yazar.
    """
    pairs = pl.read_parquet(data_dir / "szz.parquet")
    commits = pl.read_parquet(data_dir / "commits.parquet").select(
        "sha", pl.col("message").str.split("\n").list.first().alias("subject")
    )
    meta = json.loads((data_dir / "meta.json").read_text("utf-8"))
    base = (meta.get("remote_url") or "").removesuffix(".git").rstrip("/")
    grouped = pairs.group_by("fix_sha", "inducing_sha").agg(
        pl.col("path").sort().str.join(", ").alias("paths"),
        pl.col("blamed_lines").sum(),
        pl.col("fix_date").first(),
        pl.col("inducing_date").first(),
    )
    sample = grouped.sort("fix_sha", "inducing_sha").sample(min(n, grouped.height), seed=seed)
    return (
        sample.join(commits.rename({"sha": "fix_sha", "subject": "fix_subject"}), on="fix_sha")
        .join(
            commits.rename({"sha": "inducing_sha", "subject": "inducing_subject"}),
            on="inducing_sha",
        )
        .with_columns(
            (pl.lit(f"{base}/commit/") + pl.col("fix_sha")).alias("fix_url"),
            (pl.lit(f"{base}/commit/") + pl.col("inducing_sha")).alias("inducing_url"),
            pl.col("fix_date").dt.date(),
            pl.col("inducing_date").dt.date(),
            pl.lit("").alias("correct"),
            pl.lit("").alias("note"),
        )
        .select(
            "fix_sha",
            "fix_date",
            "fix_subject",
            "inducing_sha",
            "inducing_date",
            "inducing_subject",
            "paths",
            "blamed_lines",
            "fix_url",
            "inducing_url",
            "correct",
            "note",
        )  # fmt: skip
        .sort("fix_date", "inducing_date")
    )
