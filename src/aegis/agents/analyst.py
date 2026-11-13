"""Analiz ajanı: diff + gatekeeper açıklaması + hafıza kartları → bulgular (FR-30, #33)."""

from collections.abc import Sequence

from pydantic import BaseModel

from aegis.agents.injection import neutralize_delimiters
from aegis.agents.prompts import DEFAULT_VERSION, load_prompts
from aegis.diff.models import Diff, FileDiff, LineKind
from aegis.gatekeeper.base import RiskAssessment
from aegis.llm.base import Usage
from aegis.llm.structured import StructuredLLM
from aegis.memory.cards import BugCard
from aegis.models import AnalysisOutput

DEFAULT_MAX_DIFF_CHARS = 100_000
"""Prompt'a giren diff metninin üst sınırı (~25k token). Aşan dosyalar dışarıda kalır."""
DEFAULT_MAX_MEMORY_CHARS = 12_000
"""Hafıza kartlarının prompt'taki üst sınırı (~3k token). Sığmayan kartlar kırpılır ya da çıkar."""


class AnalysisResult(BaseModel):
    output: AnalysisOutput | None = None
    error: str | None = None
    prompt_version: str
    omitted_files: list[str] = []
    memory_cards: list[str] = []
    """Prompt'a giren kartların kimlikleri."""
    dropped_refs: int = 0
    """Modelin verdiği ama prompt'ta olmayan (uydurma) kart kimliği sayısı."""
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


def render_card(card: BugCard, max_chars: int | None = None) -> str:
    """Kartın prompt metni: kimlik, tarih, özet, fonksiyonlar, fix öncesi ve sonrası kod."""
    head = [f"### {card.id} · {card.fix_date.date()} · {card.summary}"]
    if card.functions:
        head.append("functions: " + ", ".join(card.functions))
    before, after = card.before or card.fix_diff, card.after
    if max_chars is not None:
        budget = max(0, max_chars - sum(len(h) + 1 for h in head) - 40)
        before = before[: budget // 2]
        after = after[: budget - len(before)]
    body = [f"before (buggy):\n{before}"]
    if after:
        body.append(f"after (fixed):\n{after}")
    return "\n".join(head + body)


def render_memory(
    cards: Sequence[BugCard], max_chars: int = DEFAULT_MAX_MEMORY_CHARS
) -> tuple[str, list[str]]:
    """Kartları bütçe içinde metne çevirir; (metin, prompt'a giren kart kimlikleri).

    Kartlar sırayla eklenir; sığmayan ilk kart kalan bütçeye kırpılır (en az 400 karakter
    kalmışsa), sonrakiler dışarıda kalır.
    """
    parts: list[str] = []
    shown: list[str] = []
    used = 0
    for card in cards:
        text = render_card(card)
        if used + len(text) > max_chars:
            remaining = max_chars - used
            if remaining < 400:
                break
            text = render_card(card, remaining)
        parts.append(text)
        shown.append(card.id)
        used += len(text)
    return "\n\n".join(parts), shown


class Analyst:
    def __init__(
        self,
        llm: StructuredLLM,
        *,
        prompt_version: str = DEFAULT_VERSION,
        language: str = "Turkish",
        max_diff_chars: int = DEFAULT_MAX_DIFF_CHARS,
        max_memory_chars: int = DEFAULT_MAX_MEMORY_CHARS,
    ) -> None:
        self.llm = llm
        self.prompts = load_prompts(prompt_version)
        self.language = language
        self.max_diff_chars = max_diff_chars
        self.max_memory_chars = max_memory_chars

    def build_prompt(
        self,
        diff: Diff,
        risk: RiskAssessment,
        metadata: str | None = None,
        cards: Sequence[BugCard] = (),
    ) -> tuple[str, list[str], list[str]]:
        """(prompt, sığmayan dosyalar, prompt'a giren kart kimlikleri)."""
        diff_text, omitted = render_diff(diff, self.max_diff_chars)
        memory_text, shown = render_memory(cards, self.max_memory_chars)
        memory_block = (
            f"<bug_memory>\n{neutralize_delimiters(memory_text)}\n</bug_memory>\n"
            if memory_text
            else ""
        )
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
            memory=memory_block,
            diff=neutralize_delimiters(diff_text),
            language=self.language,
        )
        return prompt, omitted, shown

    def analyze(
        self,
        diff: Diff,
        risk: RiskAssessment,
        metadata: str | None = None,
        cards: Sequence[BugCard] = (),
    ) -> AnalysisResult:
        """`metadata`: PR başlığı, açıklaması ve commit mesajları (güvenilmeyen veri).

        `cards`: hafızadan getirilen hata kartları. Modelin `memory_refs` alanındaki, prompt'ta
        gösterilmemiş kimlikler düşürülür.
        """
        prompt, omitted, shown = self.build_prompt(diff, risk, metadata, cards)
        result = self.llm.generate(self.prompts.system, prompt, AnalysisOutput)
        dropped = 0
        if result.value is not None:
            valid = set(shown)
            for finding in result.value.findings:
                kept = [ref for ref in finding.memory_refs if ref in valid]
                dropped += len(finding.memory_refs) - len(kept)
                finding.memory_refs = kept
        return AnalysisResult(
            output=result.value,
            error=result.error,
            prompt_version=self.prompts.version,
            omitted_files=omitted,
            memory_cards=shown,
            dropped_refs=dropped,
            usage=result.usage,
            calls=result.calls,
            cached=result.cached,
        )
