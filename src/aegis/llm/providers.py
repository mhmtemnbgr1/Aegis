"""LLM adaptörleri: yerel Ollama ve testler için Mock.

Ollama SDK'sı opsiyoneldir (`uv sync --extra ollama`) ve yalnızca adaptör oluşturulurken import
edilir. Sunucu adresi `OLLAMA_HOST` ortam değişkeninden okunur. Testler için adaptör hazır bir
istemci (`client=`) kabul eder.
"""

import importlib
import json
import os
from types import ModuleType
from typing import Any

from aegis.llm.base import LLMError, LLMRequest, LLMResponse, Usage


def _import(module: str, extra: str) -> ModuleType:
    try:
        return importlib.import_module(module)
    except ImportError as exc:
        raise LLMError(
            f"{module} kurulu değil: `uv sync --extra {extra}`", retryable=False
        ) from exc


def _nonempty(text: str | None, provider: str) -> str:
    if not text:
        raise LLMError(f"{provider}: boş yanıt")
    return text


class OllamaProvider:
    name = "ollama"

    def __init__(
        self,
        model: str,
        *,
        temperature: float | None = 0.0,
        timeout: float = 60,
        client: Any = None,
    ) -> None:
        self.model = model
        self.temperature = temperature
        if client is None:
            ollama = _import("ollama", "ollama")
            client = ollama.Client(host=os.environ.get("OLLAMA_HOST"), timeout=timeout)
        self._client = client

    def complete(self, request: LLMRequest) -> LLMResponse:
        options: dict[str, Any] = {"num_predict": request.max_tokens}
        if self.temperature is not None:
            options["temperature"] = self.temperature
        try:
            resp = self._client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": request.system},
                    {"role": "user", "content": request.prompt},
                ],
                format=request.json_schema,
                options=options,
            )
        except Exception as exc:
            raise LLMError(f"ollama: {exc}") from exc
        return LLMResponse(
            text=_nonempty(resp.message.content, self.name),
            provider=self.name,
            model=self.model,
            usage=Usage(
                input_tokens=resp.prompt_eval_count or 0,
                output_tokens=resp.eval_count or 0,
            ),
        )


class MockProvider:
    """Testler ve çevrimdışı deneyler için: sıradaki hazır yanıtı döndürür, istekleri kaydeder."""

    name = "mock"

    def __init__(self, responses: list[str | dict[str, Any]], model: str = "mock") -> None:
        self.model = model
        self._responses = list(responses)
        self.requests: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if not self._responses:
            raise LLMError("mock: yanıt kalmadı")
        item = self._responses.pop(0)
        text = item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)
        return LLMResponse(text=text, provider=self.name, model=self.model)
