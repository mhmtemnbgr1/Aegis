"""Eğitilmiş model yokken kullanılan sezgisel gatekeeper (FR-17).

Üç bileşen [0, 1] aralığına normalize edilip ağırlıklı ortalaması alınır:
değişen satır sayısı, riskli yol ve eklenen satırlardaki riskli API kullanımı.
Deneylerde taban çizgisi olarak da kullanılır.
"""

import re
from datetime import datetime
from pathlib import PurePosixPath

from aegis.config import GatekeeperConfig
from aegis.diff.models import Diff, FileDiff
from aegis.gatekeeper.base import RiskAssessment, band_for

_WORD_SPLIT = re.compile(r"[^a-z0-9]+")


def is_test_file(path: str) -> bool:
    p = PurePosixPath(path)
    return (
        "tests" in p.parts[:-1]
        or "test" in p.parts[:-1]
        or p.name.startswith("test_")
        or p.stem.endswith("_test")
        or p.name == "conftest.py"
    )


class HeuristicGatekeeper:
    def __init__(self, config: GatekeeperConfig | None = None) -> None:
        self.config = config or GatekeeperConfig()
        h = self.config.heuristic
        self._risky_paths = {p.lower() for p in h.risky_paths}
        self._risky_apis = [re.compile(pattern) for pattern in h.risky_apis]

    def _risky_path_hits(self, f: FileDiff) -> set[str]:
        words = set(_WORD_SPLIT.split(f.path.lower()))
        return words & self._risky_paths

    def _risky_api_hits(self, f: FileDiff) -> list[str]:
        if is_test_file(f.path):
            return []
        return [
            line.content.strip()
            for h in f.hunks
            for line in h.added_lines
            if any(p.search(line.content) for p in self._risky_apis)
        ]

    def assess(self, diff: Diff, *, as_of: datetime) -> RiskAssessment:
        h = self.config.heuristic
        changed = diff.added + diff.removed
        path_hits = {f.path: hits for f in diff.files if (hits := self._risky_path_hits(f))}
        api_hits = {f.path: lines for f in diff.files if (lines := self._risky_api_hits(f))}
        n_api = sum(len(v) for v in api_hits.values())

        size_score = min(1.0, changed / h.size_saturation)
        path_score = 1.0 if path_hits else 0.0
        api_score = min(1.0, n_api / h.api_saturation)
        total_weight = h.size_weight + h.path_weight + h.api_weight
        score = (
            h.size_weight * size_score + h.path_weight * path_score + h.api_weight * api_score
        ) / total_weight

        reasons = [f"{changed} satır değişti ({len(diff.files)} dosya)"]
        if path_hits:
            keywords = sorted(set().union(*path_hits.values()))
            reasons.append(f"riskli yol ({', '.join(keywords)}): {', '.join(sorted(path_hits))}")
        if api_hits:
            first_file, first_lines = next(iter(api_hits.items()))
            reasons.append(
                f"{n_api} riskli API kullanımı, ör. {first_file}: `{first_lines[0][:80]}`"
            )

        return RiskAssessment(
            score=round(score, 4),
            band=band_for(score, self.config.low_threshold, self.config.high_threshold),
            reasons=reasons,
            features={
                "changed_lines": float(changed),
                "files": float(len(diff.files)),
                "risky_path_files": float(len(path_hits)),
                "risky_api_calls": float(n_api),
                "size_score": size_score,
                "path_score": path_score,
                "api_score": api_score,
            },
        )
