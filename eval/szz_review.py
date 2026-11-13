"""SZZ eşlemelerini elle kontrol etmek için tek dosyalık HTML sayfası üretir (#9).

Her eşleme için yalnızca ilgili satırlar gösterilir:
1. Fix'in sildiği/değiştirdiği ve inducing commit'e izlenen satırlar (çevresiyle),
2. Bu satırların inducing commit'te nasıl eklendiği ya da değiştirildiği.

Sayfa karar vermez; kontrol eden kişi `evet` / `hayir` / `belirsiz` seçer. Seçimler tarayıcıda
saklanır ve "CSV indir" ile `fix_sha, inducing_sha, correct, note` olarak dışa aktarılır.

Kullanım:
    uv run python eval/szz_review.py .aegis/data/tqdm__tqdm .aegis/repos/tqdm__tqdm \
        eval/labels/szz-tqdm__tqdm.csv eval/labels/szz-tqdm__tqdm.html
"""

import html
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import polars as pl

from aegis.config import MiningConfig
from aegis.mining.szz import deleted_lines

_HEADER = re.compile(r"^([0-9a-f]{40}) (\d+) (\d+)(?: \d+)?$")
_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    ).stdout


def blame(
    repo: Path, rev: str, path: str, lines: list[int], ignore: Path | None
) -> list[dict[str, Any]]:
    """Satır başına: sha, inducing'deki no (orig), dosya adı, içerik, ebeveyndeki no (final)."""
    args = ["blame", "--porcelain", "-w"]
    if ignore is not None and ignore.is_file():
        args += ["--ignore-revs-file", str(ignore.resolve())]
    for n in sorted(set(lines)):
        args += ["-L", f"{n},{n}"]
    out: list[dict[str, Any]] = []
    filenames: dict[str, str] = {}
    current: dict[str, Any] = {}
    for line in git(repo, *args, rev, "--", path).splitlines():
        if m := _HEADER.match(line):
            current = {"sha": m.group(1), "orig": int(m.group(2)), "final": int(m.group(3))}
        elif line.startswith("filename "):
            filenames[current["sha"]] = line[len("filename ") :]
        elif line.startswith("\t"):
            current["filename"] = filenames.get(current["sha"], path)
            current["content"] = line[1:]
            out.append(current)
    return out


def hunks(diff: str) -> list[dict[str, Any]]:
    """Unified diff'i satır listeleriyle hunk'lara böler: (tür, eski no, yeni no, metin)."""
    result: list[dict[str, Any]] = []
    old = new = 0
    for line in diff.splitlines():
        if m := _HUNK.match(line):
            old, new = int(m.group(1)), int(m.group(3))
            result.append({"lines": []})
        elif not result or line.startswith(("\\", "diff ", "index ", "--- ", "+++ ")):
            continue
        elif line.startswith("-"):
            result[-1]["lines"].append(("del", old, None, line[1:]))
            old += 1
        elif line.startswith("+"):
            result[-1]["lines"].append(("add", None, new, line[1:]))
            new += 1
        else:
            result[-1]["lines"].append(("ctx", old, new, line[1:] if line else ""))
            old += 1
            new += 1
    return result


def pick(
    hs: list[dict[str, Any]], *, old: set[int] | None = None, new: set[int] | None = None
) -> list[list[Any]]:
    """Hedef satırları içeren hunk'lar; her satır [tür, no, metin, hedef mi]."""
    old, new = old or set(), new or set()
    picked: list[list[Any]] = []
    for h in hs:
        hit = any(
            (k == "del" and o in old) or (k == "add" and n in new) for k, o, n, _ in h["lines"]
        )
        if not hit:
            continue
        if picked:
            picked.append(["sep", None, "…", False])
        for kind, o, n, text in h["lines"]:
            target = (kind == "del" and o in old) or (kind == "add" and n in new)
            picked.append([kind, o if kind == "del" else n, text, target])
    return picked


def build(data_dir: Path, repo: Path, sample_csv: Path) -> list[dict[str, Any]]:
    sample = pl.read_csv(sample_csv, infer_schema=False)
    commits = pl.read_parquet(data_dir / "commits.parquet")
    parents = dict(zip(commits["sha"], commits["parents"].to_list(), strict=True))
    ignore = data_dir / ".szz-ignore-revs"
    meta = json.loads((data_dir / "szz_meta.json").read_text("utf-8"))
    config = MiningConfig(szz_variant=meta["variant"])
    ma = config.szz_variant == "ma"
    items: list[dict[str, Any]] = []
    for i, row in enumerate(sample.iter_rows(named=True), 1):
        fix, inducing = row["fix_sha"], row["inducing_sha"]
        parent = parents[fix][0]
        sections: list[dict[str, Any]] = []
        for path in row["paths"].split(", "):
            removed = deleted_lines(
                repo, parent, fix, [path], ignore_whitespace=ma, skip_useless=ma
            )
            blamed = [
                b
                for b in blame(repo, parent, path, removed.get(path, []), ignore if ma else None)
                if b["sha"] == inducing
            ]
            if not blamed:
                continue
            ws = ["-w"] if ma else []
            fix_diff = git(repo, "diff", "-U3", *ws, parent, fix, "--", path)
            fix_view = pick(hunks(fix_diff), old={b["final"] for b in blamed})
            ind_path = blamed[0]["filename"]
            ind_parents = parents.get(inducing) or []
            if ind_parents:
                ind_diff = git(repo, "diff", "-U3", ind_parents[0], inducing, "--", ind_path)
            else:  # ilk commit
                ind_diff = git(repo, "show", "-U3", "--format=", inducing, "--", ind_path)
            ind_view = pick(hunks(ind_diff), new={b["orig"] for b in blamed})
            # Hedef satırın hunk'ında silinen satır da varsa inducing satırı "değiştirmiş" demektir.
            modified = any(line[0] == "del" for line in ind_view)
            sections.append(
                {
                    "path": path,
                    "ind_path": ind_path,
                    "count": len(blamed),
                    "fix": fix_view,
                    "inducing": ind_view,
                    "modified": modified,
                }
            )
        items.append(
            {
                "no": i,
                "fix_sha": fix,
                "inducing_sha": inducing,
                "fix_subject": row["fix_subject"],
                "inducing_subject": row["inducing_subject"],
                "fix_date": row["fix_date"],
                "inducing_date": row["inducing_date"],
                "fix_url": row["fix_url"],
                "inducing_url": row["inducing_url"],
                "sections": sections,
            }
        )
    return items


def main() -> None:
    data_dir, repo, sample_csv, out = (Path(a) for a in sys.argv[1:5])
    items = build(data_dir, repo, sample_csv)
    template = (Path(__file__).parent / "szz_review_template.html").read_text("utf-8")
    page = template.replace("__TITLE__", html.escape(data_dir.name)).replace(
        "__DATA__", json.dumps(items, ensure_ascii=False).replace("</", "<\\/")
    )
    out.write_text(page, "utf-8")
    empty = sum(1 for it in items if not it["sections"])
    print(f"{len(items)} eşleme -> {out} ({empty} tanesinde satır bulunamadı)")


if __name__ == "__main__":
    main()
