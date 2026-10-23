"""Diff ayrıştırma ve ön filtre (FR-06)."""

from aegis.diff.filters import FilterResult, SkippedFile, SkipReason, filter_diff, load_ignore_spec
from aegis.diff.models import Diff, DiffLine, FileDiff, FileStatus, Hunk, LineKind
from aegis.diff.parse import git_commit_messages, git_diff, parse_diff

__all__ = [
    "Diff",
    "DiffLine",
    "FileDiff",
    "FileStatus",
    "FilterResult",
    "Hunk",
    "LineKind",
    "SkipReason",
    "SkippedFile",
    "filter_diff",
    "git_commit_messages",
    "git_diff",
    "load_ignore_spec",
    "parse_diff",
]
