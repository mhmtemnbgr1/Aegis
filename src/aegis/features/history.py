"""Zaman kuralı (`as_of`) ile sorgulanabilen değişiklik geçmişi (FR-18, #72).

Her özellik fonksiyonu zorunlu bir `as_of` alır ve geçmişi yalnızca bu sınıf üzerinden okur.
`ChangeHistory` bir olayı yalnızca **commit zamanı `as_of`'tan kesin olarak önce** ise döndürür;
böylece bir commit'in özellikleri kendisini ve sonrasını göremez. Commit zamanı (yazım değil),
olayın repoya girdiği andır: rebase edilmiş eski tarihli commit'ler de sızıntı yaratmaz.

Satır sayıları git'ten okunmaz; dosya değişiklikleri kronolojik sırayla yeniden oynatılır
(ekle → +eklenen − silinen, yeniden adlandırma geçmişi yeni yola taşır). Merge commit'leri
PyDriller'da dosya değişikliği taşımadığından olay üretmez.
"""

from bisect import bisect_left
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime

import polars as pl


def developer_id(name: str | None, email: str | None) -> str:
    """Geliştirici kimliği: küçük harf e-posta, yoksa ad."""
    return (email or name or "").strip().lower()


def subsystem(path: str) -> str:
    """Kamei'deki alt sistem: en üst dizin (kökteki dosyalar için boş dize)."""
    return path.split("/", 1)[0] if "/" in path else ""


def directory(path: str) -> str:
    return path.rsplit("/", 1)[0] if "/" in path else ""


@dataclass(frozen=True)
class FileChange:
    old_path: str | None
    new_path: str | None
    added: int
    deleted: int

    @property
    def path(self) -> str:
        """Değişiklikten sonraki yol (silinen dosyada önceki yol)."""
        return self.new_path or self.old_path or ""

    @property
    def prior_path(self) -> str | None:
        """Değişiklikten önceki yol; yeni eklenen dosyada None."""
        return self.old_path


@dataclass(frozen=True)
class Change:
    """Özelliği hesaplanacak değişiklik: geçmişteki bir commit ya da incelenen bir PR."""

    developer: str
    files: Sequence[FileChange]
    is_fix: bool = False


@dataclass
class _Events:
    """Zamana göre sıralı olaylar; paralel listeler bisect için tutulur."""

    times: list[datetime] = field(default_factory=list)
    shas: list[str] = field(default_factory=list)
    developers: list[str] = field(default_factory=list)
    deltas: list[int] = field(default_factory=list)

    def append(self, time: datetime, sha: str, developer: str, delta: int) -> None:
        self.times.append(time)
        self.shas.append(sha)
        self.developers.append(developer)
        self.deltas.append(delta)

    def count_before(self, as_of: datetime) -> int:
        return bisect_left(self.times, as_of)


class ChangeHistory:
    """Commit ve dosya olaylarının `as_of` ile sorgulanabilen dizini.

    Yeniden adlandırmalar olayları taşımaz; yeni yola zaman damgalı bir "önceki yol" bağlantısı
    eklenir. Sorgu, bağlantıyı yalnızca adlandırma `as_of`'tan önce olduysa izler; böylece
    gelecekteki bir adlandırma geçmişteki sorguların sonucunu değiştirmez.
    """

    def __init__(self) -> None:
        self._files: dict[str, _Events] = {}
        self._renamed_from: dict[str, list[tuple[datetime, str]]] = {}
        self._developers: dict[str, list[datetime]] = {}
        self._dev_subsystems: dict[tuple[str, str], _Events] = {}
        self._last_time: datetime | None = None

    # Oluşturma
    def add_commit(
        self, sha: str, time: datetime, developer: str, files: Iterable[FileChange]
    ) -> None:
        """Commit'i geçmişe ekler. Commit'ler commit zamanına göre sırayla eklenmelidir."""
        if self._last_time is not None and time < self._last_time:
            raise ValueError("commit'ler commit zamanına göre sıralı eklenmeli")
        self._last_time = time
        self._developers.setdefault(developer, []).append(time)
        for sub in {subsystem(f.path) for f in files}:
            self._dev_subsystems.setdefault((developer, sub), _Events()).append(
                time, sha, developer, 0
            )
        for f in files:
            if f.old_path and f.new_path and f.old_path != f.new_path:
                # Yeniden adlandırma: yeni yol önceki yola bağlanır, önceki yol boşalır.
                self._renamed_from.setdefault(f.new_path, []).append((time, f.old_path))
                remaining = self.line_count(f.old_path, time)
                self._files.setdefault(f.old_path, _Events()).append(
                    time, sha, developer, -remaining
                )
            events = self._files.setdefault(f.path, _Events())
            events.append(time, sha, developer, f.added - f.deleted)

    @classmethod
    def from_frames(cls, commits: pl.DataFrame, files: pl.DataFrame) -> "ChangeHistory":
        """`commits.parquet` ve `files.parquet`'ten geçmişi kurar (merge commit'leri hariç)."""
        history = cls()
        for sha, time, developer, changes in iter_changes(commits, files):
            history.add_commit(sha, time, developer, changes.files)
        return history

    # Sorgular: hepsi yalnızca commit zamanı < as_of olan olayları görür.
    def file_events(
        self, path: str, as_of: datetime
    ) -> tuple[list[datetime], list[str], list[str]]:
        """`path`'e (ve adlandırılmadan önceki yollarına) `as_of`'tan önce dokunan olayların
        zaman, sha ve geliştirici listeleri, eskiden yeniye."""
        times: list[datetime] = []
        shas: list[str] = []
        developers: list[str] = []
        for events, start, end in self._visible(path, as_of):
            times += events.times[start:end]
            shas += events.shas[start:end]
            developers += events.developers[start:end]
        return times, shas, developers

    def line_count(self, path: str, as_of: datetime) -> int:
        """`path`'in `as_of` anındaki satır sayısı (olayların yeniden oynatılmasıyla)."""
        total = sum(sum(ev.deltas[start:end]) for ev, start, end in self._visible(path, as_of))
        return max(0, total)

    def _visible(self, path: str, as_of: datetime) -> list[tuple[_Events, int, int]]:
        """`as_of`'ta görünen olay dilimleri (olaylar, başlangıç, bitiş), eskiden yeniye.

        Adlandırma bağlantısı varsa: önceki yolun adlandırmadan önceki olayları + bu yolun
        adlandırmadan itibaren olayları.
        """
        events = self._files.get(path)
        end = events.count_before(as_of) if events is not None else 0
        links = [link for link in self._renamed_from.get(path, ()) if link[0] < as_of]
        if not links:
            return [(events, 0, end)] if events is not None else []
        renamed_at, old_path = links[-1]
        older = self._visible(old_path, renamed_at)
        if events is None:
            return older
        return [*older, (events, events.count_before(renamed_at), end)]

    def developer_times(self, developer: str, as_of: datetime) -> list[datetime]:
        """Geliştiricinin `as_of`'tan önceki commit zamanları."""
        times = self._developers.get(developer, [])
        return times[: bisect_left(times, as_of)]

    def developer_subsystem_shas(
        self, developer: str, subsystems: Iterable[str], as_of: datetime
    ) -> set[str]:
        """Geliştiricinin verilen alt sistemlere `as_of`'tan önce dokunduğu commit'ler."""
        shas: set[str] = set()
        for sub in subsystems:
            events = self._dev_subsystems.get((developer, sub))
            if events is not None:
                shas.update(events.shas[: events.count_before(as_of)])
        return shas


def iter_changes(
    commits: pl.DataFrame, files: pl.DataFrame
) -> Iterable[tuple[str, datetime, str, Change]]:
    """Merge olmayan commit'leri commit zamanı sırasıyla (sha, zaman, geliştirici, Change) verir."""
    by_sha: dict[str, list[FileChange]] = {}
    for sha, old, new, added, deleted in files.select(
        "sha", "old_path", "new_path", "lines_added", "lines_deleted"
    ).iter_rows():
        by_sha.setdefault(sha, []).append(FileChange(old, new, added, deleted))
    ordered = commits.filter(~pl.col("is_merge")).sort("committer_date", maintain_order=True)
    for sha, time, name, email, is_fix in ordered.select(
        "sha", "committer_date", "author_name", "author_email", "is_fix"
    ).iter_rows():
        developer = developer_id(name, email)
        yield sha, time, developer, Change(developer, by_sha.get(sha, []), is_fix)
