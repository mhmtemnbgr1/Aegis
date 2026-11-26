"""LLM adaptörleri: yerel Ollama ve testler için Mock.

Ollama SDK'sı opsiyoneldir (`uv sync --extra ollama`) ve yalnızca adaptör oluşturulurken import
edilir. Sunucu adresi `OLLAMA_HOST` ortam değişkeninden okunur. Testler için adaptör hazır bir
istemci (`client=`) kabul eder.
"""

import importlib
import json
import math
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


CHARS_PER_TOKEN = 3.4
"""Temkinli karakter/token oranı: D2 istemlerinde ölçülen oranın alt %5'i (kod ~3,4–3,8)."""
CONTEXT_MARGIN = 256
"""Sohbet şablonunun ve şemanın token payı."""


def estimate_tokens(text: str) -> int:
    """Token sayısının temkinli (yukarı yuvarlanmış) tahmini."""
    return math.ceil(len(text) / CHARS_PER_TOKEN)


class OllamaProvider:
    """Yerel Ollama.

    `num_ctx` verilirse bağlam penceresi açıkça ayarlanır. Ollama, pencereyi aşan istemi hata
    vermeden baştan keser; bunu önlemek için istem + `max_tokens` tahmini pencereye sığmıyorsa
    pencere `max_num_ctx`'e kadar ikiye katlanır. Yanıttaki token sayısı yine de pencereyi
    doldurmuşsa (kesilme olmuş demektir) sonuç kullanılmaz, `LLMError` fırlatılır.
    `num_ctx=None` Ollama'nın varsayılanını kullanır (eski davranış).
    """

    name = "ollama"

    def __init__(
        self,
        model: str,
        *,
        temperature: float | None = 0.0,
        timeout: float = 60,
        num_ctx: int | None = None,
        max_num_ctx: int = 32_768,
        client: Any = None,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.num_ctx = num_ctx
        self.max_num_ctx = max(max_num_ctx, num_ctx or 0)
        self.last_num_ctx: int | None = None
        """Son istekte kullanılan bağlam penceresi (deney kayıtları için)."""
        if client is None:
            ollama = _import("ollama", "ollama")
            client = ollama.Client(host=os.environ.get("OLLAMA_HOST"), timeout=timeout)
        self._client = client

    def context_for(self, request: LLMRequest) -> int | None:
        """İsteğin sığacağı bağlam penceresi; `num_ctx` verilmemişse None."""
        if self.num_ctx is None:
            return None
        need = (
            estimate_tokens(request.system)
            + estimate_tokens(request.prompt)
            + request.max_tokens
            + CONTEXT_MARGIN
        )
        ctx = self.num_ctx
        while ctx < need and ctx < self.max_num_ctx:
            ctx = min(ctx * 2, self.max_num_ctx)
        return ctx

    def complete(self, request: LLMRequest) -> LLMResponse:
        options: dict[str, Any] = {"num_predict": request.max_tokens}
        if self.temperature is not None:
            options["temperature"] = self.temperature
        ctx = self.context_for(request)
        if ctx is not None:
            options["num_ctx"] = ctx
        self.last_num_ctx = ctx
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
        prompt_tokens, output_tokens = resp.prompt_eval_count or 0, resp.eval_count or 0
        if ctx is not None and prompt_tokens + output_tokens >= ctx - 8:
            raise LLMError(
                f"ollama: bağlam penceresi doldu ({prompt_tokens} + {output_tokens} / {ctx} "
                "token); istem kesilmiş olabilir, sonuç kullanılmadı",
                retryable=False,
            )
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
