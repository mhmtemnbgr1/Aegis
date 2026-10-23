import sys
from types import SimpleNamespace as NS
from typing import Any

import pytest

from aegis.config import AgentConfig
from aegis.llm import (
    AnthropicProvider,
    GeminiProvider,
    LLMError,
    LLMProvider,
    LLMRequest,
    MockProvider,
    OllamaProvider,
    OpenAIProvider,
    create_provider,
)

SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
REQ = LLMRequest(system="sys", prompt="diff", json_schema=SCHEMA, max_tokens=100)


class Recorder:
    """İstenen metot çağrısını kaydedip hazır yanıtı (veya hatayı) döndürür."""

    def __init__(self, result: Any) -> None:
        self.result = result
        self.kwargs: dict[str, Any] = {}

    def __call__(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_ollama() -> None:
    chat = Recorder(NS(message=NS(content='{"ok": true}'), prompt_eval_count=12, eval_count=3))
    provider = OllamaProvider("qwen", client=NS(chat=chat))
    resp = provider.complete(REQ)
    assert resp.text == '{"ok": true}'
    assert (resp.provider, resp.model) == ("ollama", "qwen")
    assert (resp.usage.input_tokens, resp.usage.output_tokens) == (12, 3)
    assert chat.kwargs["format"] == SCHEMA
    assert chat.kwargs["options"] == {"num_predict": 100, "temperature": 0.0}
    assert [m["role"] for m in chat.kwargs["messages"]] == ["system", "user"]


def test_gemini() -> None:
    gen = Recorder(NS(text="{}", usage_metadata=NS(prompt_token_count=5, candidates_token_count=2)))
    provider = GeminiProvider("gemini-flash", client=NS(models=NS(generate_content=gen)))
    resp = provider.complete(REQ)
    assert resp.usage.input_tokens == 5
    config = gen.kwargs["config"]
    assert config.system_instruction == "sys"
    assert config.response_json_schema == SCHEMA
    assert config.response_mime_type == "application/json"
    assert gen.kwargs["contents"] == "diff"


def test_gemini_plain_text_without_schema() -> None:
    gen = Recorder(NS(text="merhaba", usage_metadata=None))
    provider = GeminiProvider("g", client=NS(models=NS(generate_content=gen)))
    resp = provider.complete(LLMRequest(system="s", prompt="p"))
    assert resp.usage.input_tokens == 0
    assert gen.kwargs["config"].response_mime_type is None


def test_openai() -> None:
    create = Recorder(
        NS(
            choices=[NS(message=NS(content="{}"))],
            usage=NS(prompt_tokens=7, completion_tokens=1),
        )
    )
    provider = OpenAIProvider(
        "gpt", temperature=None, client=NS(chat=NS(completions=NS(create=create)))
    )
    resp = provider.complete(REQ)
    assert resp.usage.output_tokens == 1
    assert "temperature" not in create.kwargs
    assert create.kwargs["max_completion_tokens"] == 100
    assert create.kwargs["response_format"]["json_schema"]["schema"] == SCHEMA


def _claude_message(stop_reason: str = "end_turn", text: str = '{"ok": true}') -> NS:
    return NS(
        stop_reason=stop_reason,
        model="claude-opus-5-5",
        content=[NS(type="thinking", thinking=""), NS(type="text", text=text)],
        usage=NS(input_tokens=20, output_tokens=4),
    )


def test_anthropic_with_fallback_model() -> None:
    beta_create, create = Recorder(_claude_message()), Recorder(None)
    client = NS(beta=NS(messages=NS(create=beta_create)), messages=NS(create=create))
    provider = AnthropicProvider("claude-opus-5-5", effort="low", client=client)
    resp = provider.complete(REQ)
    assert resp.text == '{"ok": true}'
    assert (resp.usage.input_tokens, resp.usage.output_tokens) == (20, 4)
    kwargs = beta_create.kwargs
    assert kwargs["fallbacks"] == "default"
    assert kwargs["betas"] == ["server-side-fallback-2026-07-01"]
    assert kwargs["output_config"] == {
        "effort": "low",
        "format": {"type": "json_schema", "schema": SCHEMA},
    }
    assert "temperature" not in kwargs
    assert create.kwargs == {}


def test_anthropic_other_model_uses_plain_endpoint() -> None:
    create = Recorder(_claude_message())
    client = NS(messages=NS(create=create))
    AnthropicProvider("claude-haiku-5-5", client=client).complete(
        LLMRequest(system="s", prompt="p")
    )
    assert create.kwargs["model"] == "claude-haiku-5-5"
    assert "output_config" not in create.kwargs


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_anthropic_bad_stop_reason(stop_reason: str) -> None:
    client = NS(messages=NS(create=Recorder(_claude_message(stop_reason))))
    with pytest.raises(LLMError):
        AnthropicProvider("claude-haiku-5-5", client=client).complete(REQ)


def test_sdk_errors_are_wrapped() -> None:
    client = NS(chat=Recorder(ConnectionError("bağlantı yok")))
    with pytest.raises(LLMError, match="ollama: bağlantı yok"):
        OllamaProvider("q", client=client).complete(REQ)


def test_empty_response_is_error() -> None:
    client = NS(chat=Recorder(NS(message=NS(content=""), prompt_eval_count=0, eval_count=0)))
    with pytest.raises(LLMError, match="boş yanıt"):
        OllamaProvider("q", client=client).complete(REQ)


def test_mock_provider() -> None:
    provider: LLMProvider = MockProvider([{"ok": True}, "düz metin"])
    assert provider.complete(REQ).text == '{"ok": true}'
    assert provider.complete(REQ).text == "düz metin"
    with pytest.raises(LLMError):
        provider.complete(REQ)
    assert isinstance(provider, MockProvider)
    assert len(provider.requests) == 3


@pytest.mark.parametrize(
    ("provider", "env", "cls"),
    [
        ("ollama", None, OllamaProvider),
        ("gemini", "GEMINI_API_KEY", GeminiProvider),
        ("openai", "OPENAI_API_KEY", OpenAIProvider),
        ("anthropic", "ANTHROPIC_API_KEY", AnthropicProvider),
    ],
)
def test_create_provider(
    monkeypatch: pytest.MonkeyPatch, provider: str, env: str | None, cls: type
) -> None:
    config = AgentConfig.model_validate({"provider": provider, "model": "m"})
    if env is not None:
        monkeypatch.delenv(env, raising=False)
        with pytest.raises(LLMError, match=env):
            create_provider(config)
        monkeypatch.setenv(env, "test-key")
    created = create_provider(config)
    assert isinstance(created, cls)
    assert created.model == "m"


def test_missing_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "ollama", None)
    with pytest.raises(LLMError, match="uv sync --extra ollama"):
        OllamaProvider("q")
