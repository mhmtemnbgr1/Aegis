"""Gatekeeper seçimi: `[gatekeeper].mode` ile sezgisel kural ya da eğitilmiş model (FR-17, #66).

`model` modunda gerekenler: reponun modeli (`<models_dir>/<repo>/<ad>-none.pkl`, yoksa genel model
`<models_dir>/all/`) ve madencilik geçmişi (`<data_dir>/<repo>/commits.parquet`). Biri eksikse ya
da model puanlama sırasında hata verirse sezgisel kurala dönülür ve gerekçeye not düşülür; inceleme
hiçbir zaman bu yüzden durmaz (fail-open).

Bütçe modunda (`max_llm_pr_ratio`) bant eşikleri, model modunda puanlanmış son PR'ların
skorlarından yeniden hesaplanır (`runs.jsonl`, bkz. `score.budget_bands`).
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from aegis.config import AegisConfig
from aegis.diff.models import Diff
from aegis.gatekeeper.base import Gatekeeper, RiskAssessment
from aegis.gatekeeper.heuristic import HeuristicGatekeeper

log = logging.getLogger(__name__)


def recent_scores(runs_path: Path, window: int) -> list[float]:
    """`runs.jsonl`'de model modunda puanlanmış son `window` PR'ın skoru (eskiden yeniye)."""
    try:
        lines = runs_path.read_text("utf-8").splitlines()
    except OSError:
        return []
    scores: list[float] = []
    for line in lines:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("gatekeeper") == "model" and record.get("risk_score") is not None:
            scores.append(float(record["risk_score"]))
    return scores[-window:]


class ModelGatekeeper:
    """Eğitilmiş modeli `Gatekeeper` protokolü arkasında çalıştırır.

    Model commit düzeyinde çalıştığı için diff yerine `base..head` aralığındaki commit'leri puanlar;
    diff yalnızca hata durumunda sezgisel kurala verilir.
    """

    def __init__(
        self,
        model_path: Path,
        data_dir: Path,
        repo: Path,
        base: str,
        head: str,
        config: AegisConfig,
        recent: list[float] | None = None,
    ) -> None:
        self.model_path, self.data_dir = model_path, data_dir
        self.repo, self.base, self.head = repo, base, head
        self.config, self.recent = config, recent or []

    def assess(self, diff: Diff, *, as_of: datetime) -> RiskAssessment:
        try:
            return self._assess()
        except Exception as exc:  # fail-open: model hatası incelemeyi durdurmaz
            log.warning("model gatekeeper başarısız, sezgisel kurala dönülüyor: %s", exc)
            risk = HeuristicGatekeeper(self.config.gatekeeper).assess(diff, as_of=as_of)
            risk.reasons.append(f"model kullanılamadı ({type(exc).__name__}); sezgisel kural")
            return risk

    def _assess(self) -> RiskAssessment:
        # scikit-learn yalnızca model modunda yüklenir.
        from aegis.gatekeeper.score import load_history, range_commits, score_range

        commits = range_commits(self.repo, self.base, self.head, self.config)
        history = load_history(self.data_dir)
        result = score_range(self.model_path, commits, history, self.config, self.recent)
        reasons = [e.text for e in result.explanations] or ["aralıkta puanlanacak commit yok"]
        reasons.append(f"model: {self.model_path.parent.name}/{self.model_path.stem}")
        probs = [p for _, _, p in result.commits]
        return RiskAssessment(
            score=round(result.score, 4),
            band=result.band,
            reasons=reasons,
            features={
                "commits": float(len(commits)),
                "max_commit_prob": max(probs, default=0.0),
                "low_threshold": result.low_threshold,
                "high_threshold": result.high_threshold,
                **{f"shap_{e.feature}": e.effect for e in result.explanations},
            },
            source="model",
        )


def make_gatekeeper(
    config: AegisConfig,
    repo: Path,
    base: str,
    head: str,
    *,
    model_path: Path | None = None,
    data_root: Path | None = None,
    models_dir: Path | None = None,
) -> tuple[Gatekeeper, str | None]:
    """(gatekeeper, uyarı). Model modu istenip kurulamıyorsa uyarıyla sezgisel kural döner."""
    gk = config.gatekeeper
    if model_path is None and gk.mode != "model":
        return HeuristicGatekeeper(gk), None
    from aegis.gatekeeper.score import find_model
    from aegis.mining import repo_slug

    slug = repo_slug(repo)
    path = model_path or find_model(
        models_dir or _resolve(repo, gk.models_dir), slug, gk.model_name
    )
    data_dir = (data_root or _resolve(repo, config.mining.data_dir)) / slug
    if path is None or not path.is_file():
        return HeuristicGatekeeper(gk), "Model bulunamadı; sezgisel kural kullanılıyor."
    if not (data_dir / "commits.parquet").is_file():
        return HeuristicGatekeeper(gk), (
            f"{data_dir} altında madencilik geçmişi yok (önce aegis mine); "
            "sezgisel kural kullanılıyor."
        )
    recent = recent_scores(repo / config.review.runs_path, gk.budget_window)
    return ModelGatekeeper(path, data_dir, repo, base, head, config, recent), None


def _resolve(repo: Path, path: str) -> Path:
    """Göreli yollar önce çalışma dizininde, yoksa repo kökünde aranır."""
    p = Path(path)
    if p.is_absolute() or p.exists():
        return p
    return repo / p
