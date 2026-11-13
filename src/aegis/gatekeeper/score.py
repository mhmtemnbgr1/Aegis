"""Bir commit aralığını (`base..head`) eğitilmiş modelle puanlar (FR-11, FR-13, FR-14, #20).

1. Aralıktaki merge olmayan commit'ler ve dosya değişiklikleri git'ten okunur.
2. Reponun madencilik geçmişi (`commits.parquet`, `files.parquet`) `ChangeHistory`'ye yüklenir.
   Aralıktaki her commit'in 14 Kamei metriği kendi commit zamanında (`as_of`) hesaplanır; sonra
   commit geçmişe eklenir, böylece PR'ın sonraki commit'leri öncekileri görür.
3. Kalibre commit olasılıkları PR skoruna birleştirilir (`1 − Π(1 − pᵢ)`); bant eşikleri
   config'den ya da `max_llm_pr_ratio` bütçesinden gelir; en riskli commit açıklanır.
"""

import contextlib
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import polars as pl

from aegis.config import AegisConfig
from aegis.features.history import ChangeHistory, FileChange, developer_id
from aegis.features.kamei import kamei_metrics
from aegis.gatekeeper.base import RiskBand, band_for
from aegis.gatekeeper.explain import Explanation
from aegis.gatekeeper.model import TrainedModel
from aegis.mining.fixes import FixClassifier

_SEP, _END = "\x1f", "\x1e"


@dataclass(frozen=True)
class RangeCommit:
    sha: str
    time: datetime
    developer: str
    subject: str
    is_fix: bool
    files: tuple[FileChange, ...]


@dataclass
class ModelScore:
    score: float
    band: RiskBand
    low_threshold: float
    high_threshold: float
    model_path: Path
    commits: list[tuple[str, str, float]] = field(default_factory=list)
    """(sha, başlık, olasılık), commit sırasıyla."""
    explanations: list[Explanation] = field(default_factory=list)


def _git(repo: Path, *args: str) -> str:
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


def range_commits(repo: Path, base: str, head: str, config: AegisConfig) -> list[RangeCommit]:
    """`base..head` aralığındaki merge olmayan commit'ler, eskiden yeniye."""
    log = _git(
        repo,
        "log",
        "--reverse",
        "--no-merges",
        f"--format=%H{_SEP}%cI{_SEP}%an{_SEP}%ae{_SEP}%B{_END}",
        f"{base}..{head}",
    )
    classifier = FixClassifier(config.mining)
    out: list[RangeCommit] = []
    for record in log.split(_END):
        if not record.strip():
            continue
        sha, time, name, email, message = record.strip("\n").split(_SEP, 4)
        diff = ("diff-tree", "-r", "-M", "--root", "--no-commit-id", "-z")
        files = parse_file_changes(
            _git(repo, *diff, "--name-status", sha), _git(repo, *diff, "--numstat", sha)
        )
        out.append(
            RangeCommit(
                sha=sha,
                time=datetime.fromisoformat(time),
                developer=developer_id(name, email),
                subject=message.strip().splitlines()[0] if message.strip() else "",
                is_fix=classifier.classify(message).is_fix,
                files=files,
            )
        )
    return out


def load_history(data_dir: Path) -> ChangeHistory:
    return ChangeHistory.from_frames(
        pl.read_parquet(data_dir / "commits.parquet"), pl.read_parquet(data_dir / "files.parquet")
    )


def range_features(commits: list[RangeCommit], history: ChangeHistory) -> pl.DataFrame:
    """Her commit için 14 Kamei metriği (`as_of` = commit zamanı)."""
    from aegis.features.history import Change

    rows = []
    for c in commits:
        change = Change(c.developer, c.files, c.is_fix)
        rows.append({"sha": c.sha, **kamei_metrics(change, history, as_of=c.time)})
        # Madencilikten daha eski tarihli bir commit eklenemez: özellikleri yine as_of ile
        # doğrudur; yalnızca aralığın sonraki commit'leri onu geçmişte görmez.
        with contextlib.suppress(ValueError):
            history.add_commit(c.sha, c.time, c.developer, c.files)
    return pl.DataFrame(rows)


def find_model(models_dir: Path, slug: str, name: str = "lr") -> Path | None:
    """Önce repoya özel model, yoksa tüm repolarla eğitilmiş genel model (soğuk başlangıç)."""
    for candidate in (
        models_dir / slug / f"{name}-none.pkl",
        models_dir / "all" / f"{name}-none.pkl",
    ):
        if candidate.is_file():
            return candidate
    return None


def score_range(
    model_path: Path, commits: list[RangeCommit], history: ChangeHistory, config: AegisConfig
) -> ModelScore:
    model = TrainedModel.load(model_path)
    features = range_features(commits, history)
    probs = [float(p) for p in model.predict_proba(features)] if features.height else []
    score = model.score_pr(features) if features.height else 0.0
    gk = config.gatekeeper
    if gk.max_llm_pr_ratio is not None and model.valid_scores:
        low, high = model.thresholds(gk.max_llm_pr_ratio, gk.high_share)
    else:
        low, high = gk.low_threshold, gk.high_threshold
    return ModelScore(
        score=score,
        band=band_for(score, low, high),
        low_threshold=low,
        high_threshold=high,
        model_path=model_path,
        commits=[(c.sha, c.subject, p) for c, p in zip(commits, probs, strict=True)],
        explanations=model.explain_pr(features) if features.height else [],
    )
