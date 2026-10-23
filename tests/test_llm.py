import sys
from types import SimpleNamespace as NS
from typing import Any

import pytest

from aegis.config import AgentConfig
from aegis.llm import (
    LLMError,
    LLMProvider,
    LLMRequest,
    MockProvider,
    OllamaProvider,
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


def test_create_provider() -> None:
    config = AgentConfig.model_validate({"model": "qwen2.5-coder:7b", "temperature": 0.2})
    created = create_provider(config)
    assert isinstance(created, OllamaProvider)
    assert (created.model, created.temperature) == ("qwen2.5-coder:7b", 0.2)


def test_cloud_providers_rejected() -> None:
    from pydantic import ValidationError

    for name in ("gemini", "openai", "anthropic"):
        with pytest.raises(ValidationError):
            AgentConfig.model_validate({"provider": name})


def test_missing_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "ollama", None)
    with pytest.raises(LLMError, match="uv sync --extra ollama"):
        OllamaProvider("q")
