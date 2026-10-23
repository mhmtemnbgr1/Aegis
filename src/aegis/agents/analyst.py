"""Analiz ajanı: diff + gatekeeper açıklaması → şemaya uygun bulgular (FR-30)."""

from pydantic import BaseModel

from aegis.agents.injection import neutralize_delimiters
from aegis.agents.prompts import DEFAULT_VERSION, load_prompts
from aegis.diff.models import Diff, FileDiff, LineKind
from aegis.gatekeeper.base import RiskAssessment
from aegis.llm.base import Usage
from aegis.llm.structured import StructuredLLM
from aegis.models import AnalysisOutput

DEFAULT_MAX_DIFF_CHARS = 100_000
"""Prompt'a giren diff metninin üst sınırı (~25k token). Aşan dosyalar dışarıda kalır."""


class AnalysisResult(BaseModel):
    output: AnalysisOutput | None = None
    error: str | None = None
    prompt_version: str
    omitted_files: list[str] = []
    usage: Usage = Usage()
    calls: int = 0
    cached: bool = False


def render_file(f: FileDiff) -> str:
    """Dosya diff'ini sol sütunda YENİ satır numaralarıyla yazar (model satır gösterebilsin)."""
    header = f"### {f.path} ({f.status})"
    if f.old_path:
        header = f"### {f.path} ({f.status} from {f.old_path})"
    out = [header]
    for h in f.hunks:
        ranges = f"-{h.old_start},{h.old_length} +{h.new_start},{h.new_length}"
        out.append(f"@@ {ranges} @@ {h.section}".rstrip())
        for line in h.lines:
            number = f"{line.new_lineno:>5}" if line.new_lineno is not None else " " * 5
            marker = {LineKind.ADDED: "+", LineKind.REMOVED: "-", LineKind.CONTEXT: " "}[line.kind]
            out.append(f"{number} {marker}{line.content}")
    return "\n".join(out)


def render_diff(diff: Diff, max_chars: int = DEFAULT_MAX_DIFF_CHARS) -> tuple[str, list[str]]:
    """Diff'i prompt metnine çevirir; sınırı aşan dosyaları atlayıp listesini döndürür."""
    parts: list[str] = []
    omitted: list[str] = []
    used = 0
    for f in diff.files:
        text = render_file(f)
        if used + len(text) > max_chars:
            omitted.append(f.path)
            continue
        parts.append(text)
        used += len(text)
    return "\n\n".join(parts), omitted


class Analyst:
    def __init__(
        self,
        llm: StructuredLLM,
        *,
        prompt_version: str = DEFAULT_VERSION,
        language: str = "Turkish",
        max_diff_chars: int = DEFAULT_MAX_DIFF_CHARS,
    ) -> None:
        self.llm = llm
        self.prompts = load_prompts(prompt_version)
        self.language = language
        self.max_diff_chars = max_diff_chars

    def build_prompt(
        self, diff: Diff, risk: RiskAssessment, metadata: str | None = None
    ) -> tuple[str, list[str]]:
        diff_text, omitted = render_diff(diff, self.max_diff_chars)
        metadata_block = (
            f"<pr_metadata>\n{neutralize_delimiters(metadata.strip())}\n</pr_metadata>\n"
            if metadata and metadata.strip()
            else ""
        )
        omitted_note = f"Not reviewed (size limit): {', '.join(omitted)}\n" if omitted else ""
        prompt = self.prompts.user.format(
            examples=self.prompts.examples.strip(),
            risk_score=f"{risk.score:.2f}",
            risk_band=risk.band,
            risk_reasons="\n".join(f"- {r}" for r in risk.reasons) or "- (none)",
            omitted=omitted_note,
            metadata=metadata_block,
            diff=neutralize_delimiters(diff_text),
            language=self.language,
        )
        return prompt, omitted

    def analyze(
        self, diff: Diff, risk: RiskAssessment, metadata: str | None = None
    ) -> AnalysisResult:
        """`metadata`: PR başlığı, açıklaması ve commit mesajları (güvenilmeyen veri)."""
        prompt, omitted = self.build_prompt(diff, risk, metadata)
        result = self.llm.generate(self.prompts.system, prompt, AnalysisOutput)
        return AnalysisResult(
            output=result.value,
            error=result.error,
            prompt_version=self.prompts.version,
            omitted_files=omitted,
            usage=result.usage,
            calls=result.calls,
            cached=result.cached,
        )
