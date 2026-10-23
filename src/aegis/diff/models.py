"""Unified diff için dosya / hunk / satır modeli."""

from enum import StrEnum

from pydantic import BaseModel, Field


class LineKind(StrEnum):
    ADDED = "added"
    REMOVED = "removed"
    CONTEXT = "context"


class FileStatus(StrEnum):
    ADDED = "added"
    DELETED = "deleted"
    MODIFIED = "modified"
    RENAMED = "renamed"


class DiffLine(BaseModel):
    kind: LineKind
    content: str
    old_lineno: int | None = None
    new_lineno: int | None = None


class Hunk(BaseModel):
    old_start: int
    old_length: int
    new_start: int
    new_length: int
    section: str = ""
    lines: list[DiffLine] = Field(default_factory=list)

    @property
    def added_lines(self) -> list[DiffLine]:
        return [line for line in self.lines if line.kind is LineKind.ADDED]

    @property
    def removed_lines(self) -> list[DiffLine]:
        return [line for line in self.lines if line.kind is LineKind.REMOVED]


class FileDiff(BaseModel):
    path: str
    """Değişiklik sonrası yol; silinen dosyalarda eski yol."""
    old_path: str | None = None
    """Yalnızca yeniden adlandırmalarda dolu."""
    status: FileStatus
    is_binary: bool = False
    hunks: list[Hunk] = Field(default_factory=list)

    @property
    def added(self) -> int:
        return sum(len(h.added_lines) for h in self.hunks)

    @property
    def removed(self) -> int:
        return sum(len(h.removed_lines) for h in self.hunks)

    @property
    def changed_new_lines(self) -> set[int]:
        """Yeni dosyada eklenen satır numaraları (satır yorumu ve kanıt kontrolü için)."""
        return {
            line.new_lineno
            for h in self.hunks
            for line in h.added_lines
            if line.new_lineno is not None
        }


class Diff(BaseModel):
    files: list[FileDiff] = Field(default_factory=list)

    @property
    def added(self) -> int:
        return sum(f.added for f in self.files)

    @property
    def removed(self) -> int:
        return sum(f.removed for f in self.files)

    def get(self, path: str) -> FileDiff | None:
        return next((f for f in self.files if f.path == path), None)
