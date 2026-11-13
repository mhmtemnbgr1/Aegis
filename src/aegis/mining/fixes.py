"""Fix-commit tespiti (FR-02).

Bir commit iki yoldan fix sayılır:

1. Mesajı bir fix kalıbıyla eşleşir (`fix`, `bug`, `regression`, `leak`, `crash` ...) ve ilk satırı
   bir dışlama kalıbıyla (`typo`, `docs`, `lint`, `Revert` ...) eşleşmez.
2. Mesajın bağladığı issue'lardan biri hata etiketi taşır (`bug` ...). Bu sinyal dışlamayı ezer.

`closes #N` gibi kapatma ifadeleri tek başına fix sayılmaz: kapatılan issue bir özellik isteği de
olabilir. Bağlanan issue numaraları kaydedilir ve etiket bilgisi varsa karar onunla verilir.
Merge commit'leri hiçbir zaman fix sayılmaz; değişiklikleri kendi commit'lerinde görülür.
"""

import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass

from aegis.config import MiningConfig

# `#123` veya `gh-123`; `owner/repo#123` (başka repo) ve `abc#1` hariç.
_ISSUE_REF = re.compile(r"(?:(?<![\w/#])#|\bgh-)(\d+)\b", re.IGNORECASE)
_CLOSING_REF = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b\s*:?\s+(?:#|gh-)(\d+)\b", re.IGNORECASE
)


@dataclass(frozen=True)
class FixClassification:
    is_fix: bool
    signals: tuple[str, ...]
    """Karara giren sinyaller, ör. `keyword:fix`, `label:bug#12`, `closes:12`, `excluded:typo`."""
    linked_issues: tuple[int, ...]


def linked_issues(message: str) -> tuple[int, ...]:
    """Mesajda geçen issue/PR numaraları, ilk görülme sırasıyla ve tekrarsız."""
    seen: dict[int, None] = {}
    for match in _ISSUE_REF.finditer(message):
        seen.setdefault(int(match.group(1)), None)
    return tuple(seen)


class FixClassifier:
    def __init__(self, config: MiningConfig | None = None) -> None:
        config = config or MiningConfig()
        self._patterns = [re.compile(p, re.IGNORECASE) for p in config.fix_patterns]
        self._excludes = [re.compile(p, re.IGNORECASE) for p in config.fix_exclude_patterns]
        self._bug_labels = {label.strip().lower() for label in config.bug_labels}
        self._subject_only = config.fix_subject_only

    def classify(
        self,
        message: str,
        *,
        is_merge: bool = False,
        issue_labels: Mapping[int, Collection[str]] | None = None,
    ) -> FixClassification:
        """`issue_labels`: issue numarası → etiket adları (biliniyorsa)."""
        issues = linked_issues(message)
        signals: list[str] = [f"closes:{n}" for n in _closing_refs(message)]
        if is_merge:
            return FixClassification(False, (*signals, "merge"), issues)

        subject = message.strip().splitlines()[0] if message.strip() else ""
        text = subject if self._subject_only else message
        keyword = next((m.group(0).lower() for p in self._patterns if (m := p.search(text))), None)
        excluded = next(
            (m.group(0).lower() for p in self._excludes if (m := p.search(subject))), None
        )
        labelled = [
            f"label:{label.strip().lower()}#{n}"
            for n in issues
            for label in (issue_labels or {}).get(n, ())
            if label.strip().lower() in self._bug_labels
        ]

        if keyword:
            signals.append(f"keyword:{keyword}")
        if keyword and excluded:
            signals.append(f"excluded:{excluded}")
        signals.extend(labelled)
        is_fix = bool(labelled) or (keyword is not None and excluded is None)
        return FixClassification(is_fix, tuple(signals), issues)


def _closing_refs(message: str) -> list[int]:
    seen: dict[int, None] = {}
    for match in _CLOSING_REF.finditer(message):
        seen.setdefault(int(match.group(1)), None)
    return list(seen)
