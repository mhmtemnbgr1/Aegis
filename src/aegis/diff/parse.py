"""Git diff metnini `Diff` modeline çevirir."""

import subprocess
from pathlib import Path

from unidiff.constants import LINE_TYPE_ADDED, LINE_TYPE_CONTEXT, LINE_TYPE_REMOVED
from unidiff.patch import PatchedFile, PatchSet

from aegis.diff.models import Diff, DiffLine, FileDiff, FileStatus, Hunk, LineKind

_LINE_KINDS = {
    LINE_TYPE_ADDED: LineKind.ADDED,
    LINE_TYPE_REMOVED: LineKind.REMOVED,
    LINE_TYPE_CONTEXT: LineKind.CONTEXT,
}


def _strip_prefix(path: str) -> str:
    return path[2:] if path.startswith(("a/", "b/")) else path


def _status(pf: PatchedFile) -> FileStatus:
    if pf.is_added_file:
        return FileStatus.ADDED
    if pf.is_removed_file:
        return FileStatus.DELETED
    if pf.is_rename:
        return FileStatus.RENAMED
    return FileStatus.MODIFIED


def _convert_file(pf: PatchedFile) -> FileDiff:
    status = _status(pf)
    hunks = [
        Hunk(
            old_start=h.source_start,
            old_length=h.source_length,
            new_start=h.target_start,
            new_length=h.target_length,
            section=h.section_header,
            lines=[
                DiffLine(
                    kind=_LINE_KINDS[line.line_type],
                    content=line.value.rstrip("\r\n"),
                    old_lineno=line.source_line_no,
                    new_lineno=line.target_line_no,
                )
                for line in h
                if line.line_type in _LINE_KINDS
            ],
        )
        for h in pf
    ]
    return FileDiff(
        path=pf.path,
        old_path=_strip_prefix(pf.source_file) if status is FileStatus.RENAMED else None,
        status=status,
        is_binary=pf.is_binary_file,
        hunks=hunks,
    )


def parse_diff(text: str) -> Diff:
    """`git diff` çıktısını ayrıştırır. Boş metin boş bir `Diff` döndürür."""
    return Diff(files=[_convert_file(pf) for pf in PatchSet(text)])


def git_diff(base: str, head: str = "HEAD", repo: Path | str = ".") -> str:
    """`base...head` aralığının diff'ini (yeniden adlandırma tespitiyle) döndürür."""
    result = subprocess.run(
        [
            "git",
            "-c",
            "core.quotepath=false",
            "diff",
            "--no-color",
            "--no-ext-diff",
            "-M",
            f"{base}...{head}",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return result.stdout
