import logging
from pathlib import Path

import pytest
from pydantic import BaseModel
from tenacity import wait_none

from aegis.llm import LLMError, LLMRequest, LLMResponse, MockProvider, Usage
from aegis.llm.cache import ResponseCache, cache_key
from aegis.llm.structured import SchemaStats, StructuredLLM, parse_json_output


class Verdict(BaseModel):
    ok: bool
    reason: str


GOOD = {"ok": True, "reason": "temiz"}


class FlakyProvider:
    """Önce verilen hataları fırlatır, sonra sabit bir yanıt döndürür."""

    name = "flaky"
    model = "m"

    def __init__(self, errors: list[LLMError], text: str = '{"ok": false, "reason": "x"}') -> None:
        self.errors = list(errors)
        self.text = text
        self.calls = 0

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return LLMResponse(text=self.text, provider=self.name, model=self.model)


def _llm(provider: object, **kwargs: object) -> StructuredLLM:
    return StructuredLLM(provider, wait=wait_none(), **kwargs)  # type: ignore[arg-type]


def test_parse_json_output_accepts_fences() -> None:
    assert parse_json_output('```json\n{"ok": true, "reason": "a"}\n```', Verdict).ok
    assert parse_json_output('{"ok": false, "reason": "b"}', Verdict).reason == "b"


def test_valid_first_try() -> None:
    provider = MockProvider([GOOD])
    result = _llm(provider).generate("sys", "diff", Verdict)
    assert result.value == Verdict(ok=True, reason="temiz")
    assert (result.calls, result.repaired, result.error) == (1, False, None)
    assert provider.requests[0].json_schema == Verdict.model_json_schema()


def test_repair_once() -> None:
    stats = SchemaStats()
    provider = MockProvider(['{"ok": "belki"}', GOOD])
    result = _llm(provider, stats=stats).generate("sys", "diff", Verdict)
    assert result.value is not None
    assert result.repaired
    assert result.calls == 2
    repair_prompt = provider.requests[1].prompt
    assert repair_prompt.startswith("diff")
    assert "reason" in repair_prompt  # eksik alan hata mesajında
    assert '{"ok": "belki"}' in repair_prompt
    assert stats.counts["repaired"] == 1


def test_repair_fails_is_fail_open() -> None:
    stats = SchemaStats()
    result = _llm(MockProvider(["bu JSON değil", "hâlâ değil"]), stats=stats).generate(
        "s", "p", Verdict
    )
    assert result.value is None
    assert result.error is not None and "şema" in result.error
    assert result.calls == 2
    assert stats.compliance_rate == 0.0


def test_transient_errors_are_retried() -> None:
    provider = FlakyProvider([LLMError("zaman aşımı"), LLMError("429")])
    result = _llm(provider, max_attempts=3).generate("s", "p", Verdict)
    assert result.value is not None
    assert provider.calls == result.calls == 3


def test_fatal_error_not_retried() -> None:
    provider = FlakyProvider([LLMError("reddedildi", retryable=False)])
    result = _llm(provider).generate("s", "p", Verdict)
    assert result.value is None
    assert result.error == "reddedildi"
    assert provider.calls == 1


def test_exhausted_retries_fail_open(caplog: pytest.LogCaptureFixture) -> None:
    provider = FlakyProvider([LLMError("down")] * 5)
    stats = SchemaStats()
    with caplog.at_level(logging.INFO, logger="aegis.llm.structured"):
        result = _llm(provider, max_attempts=2, stats=stats).generate("s", "p", Verdict)
    assert result.value is None
    assert provider.calls == 2
    assert stats.counts["error"] == 1
    assert stats.total == 0  # API hatası şema uyumunu etkilemez
    assert "fail-open" in caplog.text
    assert "şema uyum oranı" in caplog.text


def test_cache_prevents_second_call(tmp_path: Path) -> None:
    cache = ResponseCache(tmp_path)
    provider = MockProvider([GOOD])  # yalnızca bir yanıt var
    first = _llm(provider, cache=cache).generate("s", "p", Verdict)
    second = _llm(provider, cache=cache).generate("s", "p", Verdict)
    assert first.value == second.value
    assert (first.cached, second.cached) == (False, True)
    assert second.calls == 0
    assert len(provider.requests) == 1


def test_repaired_answer_cached_under_original_request(tmp_path: Path) -> None:
    cache = ResponseCache(tmp_path)
    provider = MockProvider(["bozuk", GOOD])
    _llm(provider, cache=cache).generate("s", "p", Verdict)
    again = _llm(provider, cache=cache).generate("s", "p", Verdict)
    assert again.cached and again.value is not None
    assert len(provider.requests) == 2


def test_invalid_responses_not_cached(tmp_path: Path) -> None:
    cache = ResponseCache(tmp_path)
    _llm(MockProvider(["bozuk", "bozuk"]), cache=cache).generate("s", "p", Verdict)
    assert list(tmp_path.rglob("*.json")) == []


def test_cache_key_depends_on_everything() -> None:
    base = LLMRequest(system="s", prompt="p")
    key = cache_key("ollama", "m", base)
    assert key == cache_key("ollama", "m", LLMRequest(system="s", prompt="p"))
    assert key != cache_key("gemini", "m", base)
    assert key != cache_key("ollama", "m2", base)
    assert key != cache_key("ollama", "m", base.model_copy(update={"prompt": "q"}))
    assert key != cache_key("ollama", "m", base.model_copy(update={"max_tokens": 1}))


def test_corrupt_cache_entry_is_miss(tmp_path: Path) -> None:
    cache = ResponseCache(tmp_path)
    cache.put("ab" + "0" * 62, LLMResponse(text="x", provider="p", model="m", usage=Usage()))
    path = next(tmp_path.rglob("*.json"))
    path.write_text("{bozuk", encoding="utf-8")
    assert cache.get("ab" + "0" * 62) is None


def test_usage_is_summed() -> None:
    class CountingProvider(FlakyProvider):
        def complete(self, request: LLMRequest) -> LLMResponse:
            text = "bozuk" if self.calls == 0 else '{"ok": true, "reason": "r"}'
            self.calls += 1
            return LLMResponse(
                text=text, provider="c", model="m", usage=Usage(input_tokens=10, output_tokens=2)
            )

    result = _llm(CountingProvider([])).generate("s", "p", Verdict)
    assert (result.usage.input_tokens, result.usage.output_tokens) == (20, 4)


def test_stats_without_data() -> None:
    assert SchemaStats().compliance_rate == 1.0
