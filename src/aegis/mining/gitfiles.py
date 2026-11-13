"""Git'ten dosya değişikliklerini okuma (`git diff-tree -z`), yeniden adlandırmalar dahil."""

import subprocess
from pathlib import Path

from aegis.features.history import FileChange

_DIFF = ("diff-tree", "-r", "-M", "--no-commit-id", "-z")


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    ).stdout


def parse_file_changes(name_status: str, numstat: str) -> tuple[FileChange, ...]:
    """`git diff-tree -z --name-status` ve `--numstat` çıktılarından dosya değişiklikleri."""
    paths: list[tuple[str | None, str | None]] = []
    tokens = name_status.lstrip("\n").split("\0")
    i = 0
    while i < len(tokens) and tokens[i]:
        status = tokens[i][0]
        if status in "RC":
            old, new = tokens[i + 1], tokens[i + 2]
            paths.append((old if status == "R" else None, new))
            i += 3
        else:
            path = tokens[i + 1]
            paths.append((None if status == "A" else path, None if status == "D" else path))
            i += 2
    counts: dict[str, tuple[int, int]] = {}
    tokens = numstat.lstrip("\n").split("\0")
    i = 0
    while i < len(tokens) and tokens[i]:
        added, deleted, path = tokens[i].split("\t", 2)
        if path:
            i += 1
        else:  # yeniden adlandırma: eski ve yeni yol ayrı alanlarda
            path = tokens[i + 2]
            i += 3
        counts[path] = (int(added) if added != "-" else 0, int(deleted) if deleted != "-" else 0)
    return tuple(FileChange(old, new, *counts.get(new or old or "", (0, 0))) for old, new in paths)


def file_changes(repo: Path, sha: str) -> tuple[FileChange, ...]:
    """Bir commit'in ilk ebeveynine göre dosya değişiklikleri (kök commit'te boş ağaca göre)."""
    return parse_file_changes(
        git(repo, *_DIFF, "--root", "--name-status", sha),
        git(repo, *_DIFF, "--root", "--numstat", sha),
    )


def tree_changes(repo: Path, base: str, head: str) -> tuple[FileChange, ...]:
    """İki commit arasındaki birleşik diff'in dosya değişiklikleri (ör. PR: merge-base..head)."""
    return parse_file_changes(
        git(repo, *_DIFF, "--name-status", base, head),
        git(repo, *_DIFF, "--numstat", base, head),
    )
