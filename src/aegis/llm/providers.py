"""Ollama, Gemini, OpenAI ve Anthropic adaptörleri.

SDK'lar opsiyoneldir (`uv sync --extra <ad>`); yalnızca ilgili adaptör oluşturulurken import
edilir. API anahtarları yalnızca ortam değişkenlerinden okunur. Testler için her adaptör hazır
bir istemci (`client=`) kabul eder.
"""

import importlib
import json
import os
from types import ModuleType
from typing import Any

from aegis.llm.base import LLMError, LLMRequest, LLMResponse, Usage

ANTHROPIC_FALLBACK_MODELS = frozenset(
    {"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}
)
"""Sunucu tarafı ret yedeği (`fallbacks="default"`) desteklenen Claude modelleri."""


def _import(module: str, extra: str) -> ModuleType:
    try:
        return importlib.import_module(module)
    except ImportError as exc:
        raise LLMError(
            f"{module} kurulu değil: `uv sync --extra {extra}`", retryable=False
        ) from exc


def _require_env(var: str) -> str:
    value = os.environ.get(var)
    if not value:
        raise LLMError(f"{var} ortam değişkeni tanımlı değil", retryable=False)
    return value


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


class GeminiProvider:
    name = "gemini"

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
        self._types = _import("google.genai.types", "gemini")
        if client is None:
            genai = _import("google.genai", "gemini")
            client = genai.Client(
                api_key=_require_env("GEMINI_API_KEY"),
                http_options=self._types.HttpOptions(timeout=int(timeout * 1000)),
            )
        self._client = client

    def complete(self, request: LLMRequest) -> LLMResponse:
        config = self._types.GenerateContentConfig(
            system_instruction=request.system,
            temperature=self.temperature,
            max_output_tokens=request.max_tokens,
            response_mime_type="application/json" if request.json_schema else None,
            response_json_schema=request.json_schema,
        )
        try:
            resp = self._client.models.generate_content(
                model=self.model, contents=request.prompt, config=config
            )
        except Exception as exc:
            raise LLMError(f"gemini: {exc}") from exc
        meta = resp.usage_metadata
        return LLMResponse(
            text=_nonempty(resp.text, self.name),
            provider=self.name,
            model=self.model,
            usage=Usage(
                input_tokens=(meta.prompt_token_count or 0) if meta else 0,
                output_tokens=(meta.candidates_token_count or 0) if meta else 0,
            ),
        )


class OpenAIProvider:
    name = "openai"

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
            openai = _import("openai", "openai")
            client = openai.OpenAI(api_key=_require_env("OPENAI_API_KEY"), timeout=timeout)
        self._client = client

    def complete(self, request: LLMRequest) -> LLMResponse:
        kwargs: dict[str, Any] = {}
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        if request.json_schema is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "aegis_output", "schema": request.json_schema},
            }
        try:
            resp = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": request.system},
                    {"role": "user", "content": request.prompt},
                ],
                max_completion_tokens=request.max_tokens,
                **kwargs,
            )
        except Exception as exc:
            raise LLMError(f"openai: {exc}") from exc
        usage = resp.usage
        return LLMResponse(
            text=_nonempty(resp.choices[0].message.content, self.name),
            provider=self.name,
            model=self.model,
            usage=Usage(
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
            ),
        )


class AnthropicProvider:
    """Claude Messages API.

    Güncel Claude modelleri `temperature` kabul etmediği için gönderilmez; yapılandırılmış çıktı
    `output_config.format` ile alınır. Destekleyen modellerde güvenlik reddine karşı sunucu
    tarafı yedek model (`fallbacks="default"`) açıktır.
    """

    name = "anthropic"

    def __init__(
        self,
        model: str,
        *,
        effort: str | None = None,
        timeout: float = 60,
        client: Any = None,
    ) -> None:
        self.model = model
        self.effort = effort
        if client is None:
            anthropic = _import("anthropic", "anthropic")
            _require_env("ANTHROPIC_API_KEY")
            client = anthropic.Anthropic(timeout=timeout)
        self._client = client

    def complete(self, request: LLMRequest) -> LLMResponse:
        output_config: dict[str, Any] = {}
        if self.effort is not None:
            output_config["effort"] = self.effort
        if request.json_schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": request.json_schema}
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": request.max_tokens,
            "system": request.system,
            "messages": [{"role": "user", "content": request.prompt}],
        }
        if output_config:
            kwargs["output_config"] = output_config
        try:
            if self.model in ANTHROPIC_FALLBACK_MODELS:
                resp = self._client.beta.messages.create(
                    betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs
                )
            else:
                resp = self._client.messages.create(**kwargs)
        except Exception as exc:
            raise LLMError(f"anthropic: {exc}") from exc
        if resp.stop_reason == "refusal":
            raise LLMError("anthropic: model isteği reddetti", retryable=False)
        if resp.stop_reason == "max_tokens":
            raise LLMError("anthropic: yanıt max_tokens sınırında kesildi", retryable=False)
        text = "".join(block.text for block in resp.content if block.type == "text")
        return LLMResponse(
            text=_nonempty(text, self.name),
            provider=self.name,
            model=resp.model,
            usage=Usage(
                input_tokens=resp.usage.input_tokens, output_tokens=resp.usage.output_tokens
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
