"""Hata kartları: geçmiş fix commit'lerinden hafıza kayıtları (FR-20, #22).

Şema `docs/architecture.md` §4 ile birebirdir. Her fix commit'i (merge olmayan, en fazla
`max_files_per_commit` dosya değiştiren ve en az bir kaynak dosyaya dokunan) bir kart olur:

- `files`: değişen kaynak dosyaları (test dosyaları hariç),
- `functions`: fix'in değiştirdiği fonksiyonların nitelikli adları (`ast`, bkz. `chunk`),
- `before` / `after`: bu fonksiyonların fix öncesi ve sonrası kodu (kırpılmış),
- `fix_diff`: kaynak dosyalarının birleşik diff'i (kırpılmış),
- `inducing_shas`: SZZ'nin bu fix için bulduğu bug-inducing commit'ler (olmayabilir),
- `issue`: mesajdaki ilk issue numarası; başlık yalnızca bir issue kaynağı verilirse dolar,
- `summary`: şimdilik commit başlığı. LLM özeti gerçek model koşularıyla gelecek.

Kartlar repo başına `<data_dir>/<repo>/cards.jsonl` dosyasına yazılır.
"""

import json
import re
from collections.abc import Callable, Collection, Iterator, Mapping
from datetime import datetime
from pathlib import Path

import polars as pl
from pydantic import BaseModel

from aegis.config import AegisConfig
from aegis.memory.chunk import changed_lines, extract, functions, touched
from aegis.mining.gitfiles import git

IssueTitles = Callable[[Collection[int]], Mapping[int, str | None]]
"""Issue numaraları → başlık (bulunamazsa None); ör. GitHub'dan, diskte cache'li."""


class Issue(BaseModel):
    number: int
    title: str | None = None


class BugCard(BaseModel):
    id: str
    fix_sha: str
    fix_date: datetime
    inducing_shas: list[str]
    issue: Issue | None
    files: list[str]
    functions: list[str]
    message: str
    before: str
    after: str
    fix_diff: str
    summary: str


def card_id(fix_sha: str) -> str:
    return f"BC-{fix_sha[:10]}"


def _show(repo: Path, rev: str, path: str) -> str:
    try:
        return git(repo, "show", f"{rev}:{path}")
    except Exception:  # dosya o sürümde yok (eklendi/silindi)
        return ""


def build_card(
    repo: Path,
    fix: dict[str, object],
    sources: list[tuple[str | None, str | None]],
    inducing: list[str],
    config: AegisConfig,
    issue: Issue | None = None,
) -> BugCard:
    """Tek bir fix commit'inin kartı.

    `sources`: değişen kaynak dosyalarının (eski, yeni) yolları.
    """
    mem = config.memory
    sha, parent = str(fix["sha"]), str(fix["parent"])
    message = str(fix["message"]).strip()
    names: list[str] = []
    before: list[str] = []
    after: list[str] = []
    for old_path, new_path in sources:
        diff = git(
            repo, "diff", "-U0", "-M", parent, sha, "--", *{p for p in (old_path, new_path) if p}
        )
        old_lines, new_lines = changed_lines(diff)
        old_src = _show(repo, parent, old_path) if old_path else ""
        new_src = _show(repo, sha, new_path) if new_path else ""
        old_hit = touched(functions(old_src, old_path or ""), old_lines) if old_src else []
        new_hit = touched(functions(new_src, new_path or ""), new_lines) if new_src else []
        for span in new_hit or old_hit:
            if span.qualname not in names:
                names.append(span.qualname)
        before += [extract(old_src, s, mem.max_code_lines, old_lines) for s in old_hit]
        after += [extract(new_src, s, mem.max_code_lines, new_lines) for s in new_hit]
    paths = sorted({p for pair in sources for p in pair if p})
    diff_lines = git(repo, "diff", "-U3", "-M", parent, sha, "--", *paths).splitlines()
    if len(diff_lines) > mem.max_diff_lines:
        diff_lines = [*diff_lines[: mem.max_diff_lines], f"... ({len(diff_lines)} satırın ilki)"]
    k = mem.max_functions_per_card
    return BugCard(
        id=card_id(sha),
        fix_sha=sha,
        fix_date=fix["committer_date"],  # type: ignore[arg-type]
        inducing_shas=inducing,
        issue=issue,
        files=sorted({new or old or "" for old, new in sources}),
        functions=names[:k],
        message=message,
        before="\n\n".join(before[:k]),
        after="\n\n".join(after[:k]),
        fix_diff="\n".join(diff_lines),
        summary=message.splitlines()[0] if message else "",
    )


def build_cards(
    repo: Path,
    data_dir: Path,
    config: AegisConfig | None = None,
    *,
    issue_titles: IssueTitles | None = None,
    skip: Collection[str] = (),
    on_card: Callable[[], None] | None = None,
) -> Iterator[BugCard]:
    """Madencilik çıktısındaki fix commit'lerinin kartları, eskiden yeniye.

    `skip`: zaten kartı olan fix SHA'ları (artımlı güncelleme için).
    """
    config = config or AegisConfig()
    mining = config.mining
    tests = [re.compile(p) for p in mining.test_path_patterns]
    commits = pl.read_parquet(data_dir / "commits.parquet")
    files = pl.read_parquet(data_dir / "files.parquet")
    szz_path = data_dir / "szz.parquet"
    inducing: dict[str, list[str]] = {}
    if szz_path.is_file():
        for fix_sha, shas in (
            pl.read_parquet(szz_path)
            .group_by("fix_sha")
            .agg(pl.col("inducing_sha").unique().sort())
            .iter_rows()
        ):
            inducing[fix_sha] = list(shas)

    def is_source(path: str | None) -> bool:
        if not path or not path.endswith(tuple(mining.source_extensions)):
            return False
        return not any(t.search(path) for t in tests)

    fixes = (
        commits.filter(
            pl.col("is_fix")
            & ~pl.col("is_merge")
            & (pl.col("files_changed") <= mining.max_files_per_commit)
            & (pl.col("parents").list.len() > 0)
            & ~pl.col("sha").is_in(list(skip))
        )
        .with_columns(pl.col("parents").list.first().alias("parent"))
        .sort("committer_date")
    )
    by_sha: dict[str, list[tuple[str | None, str | None]]] = {}
    for sha, old, new in files.select("sha", "old_path", "new_path").iter_rows():
        if is_source(new) or is_source(old):
            by_sha.setdefault(sha, []).append((old, new))
    numbers: dict[str, int] = {}
    for sha, issues in fixes.select("sha", "linked_issues").iter_rows():
        if sha in by_sha and issues:
            numbers[sha] = int(issues[0])
    titles = issue_titles(sorted(set(numbers.values()))) if issue_titles and numbers else {}
    for fix in fixes.iter_rows(named=True):
        sources = by_sha.get(fix["sha"])
        if not sources:
            continue
        number = numbers.get(fix["sha"])
        issue = Issue(number=number, title=titles.get(number)) if number is not None else None
        yield build_card(repo, fix, sources, inducing.get(fix["sha"], []), config, issue)
        if on_card is not None:
            on_card()


def write_cards(
    path: Path, cards: Iterator[BugCard] | list[BugCard], *, append: bool = False
) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("a" if append else "w", encoding="utf-8") as fh:
        for card in cards:
            fh.write(card.model_dump_json() + "\n")
            n += 1
    return n


def read_cards(path: Path) -> list[BugCard]:
    if not path.is_file():
        return []
    return [
        BugCard.model_validate(json.loads(line))
        for line in path.read_text("utf-8").splitlines()
        if line.strip()
    ]
