"""Eğitilmiş model yokken kullanılan sezgisel gatekeeper (FR-17).

İki bileşen [0, 1] aralığına normalize edilip ağırlıklı ortalaması alınır:
değişen satır sayısı ve riskli yol (`auth`, `db`, `payment`…).
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

    def _risky_path_hits(self, f: FileDiff) -> set[str]:
        words = set(_WORD_SPLIT.split(f.path.lower()))
        return words & self._risky_paths

    def assess(self, diff: Diff, *, as_of: datetime) -> RiskAssessment:
        h = self.config.heuristic
        changed = diff.added + diff.removed
        path_hits = {f.path: hits for f in diff.files if (hits := self._risky_path_hits(f))}

        size_score = min(1.0, changed / h.size_saturation)
        path_score = 1.0 if path_hits else 0.0
        score = (h.size_weight * size_score + h.path_weight * path_score) / (
            h.size_weight + h.path_weight
        )

        reasons = [f"{changed} satır değişti ({len(diff.files)} dosya)"]
        if path_hits:
            keywords = sorted(set().union(*path_hits.values()))
            reasons.append(f"riskli yol ({', '.join(keywords)}): {', '.join(sorted(path_hits))}")

        return RiskAssessment(
            score=round(score, 4),
            band=band_for(score, self.config.low_threshold, self.config.high_threshold),
            reasons=reasons,
            features={
                "changed_lines": float(changed),
                "files": float(len(diff.files)),
                "risky_path_files": float(len(path_hits)),
                "size_score": size_score,
                "path_score": path_score,
            },
        )
