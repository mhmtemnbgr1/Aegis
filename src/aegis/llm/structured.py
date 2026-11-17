"""Yapılandırılmış çıktı: şema doğrulama, tek düzeltme denemesi, retry ve cache.

Hiçbir hata dışarı sızmaz (fail-open, NFR-01): sonuç `StructuredResult.value is None` ve
`error` dolu olarak döner; çağıran taraf incelemeyi LLM'siz sürdürür.
"""

import logging
import re
from collections import Counter

from pydantic import BaseModel, ValidationError
from tenacity import (
    RetryError,
    Retrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)
from tenacity.wait import wait_base

from aegis.llm.base import LLMError, LLMProvider, LLMRequest, LLMResponse, Usage
from aegis.llm.cache import ResponseCache, cache_key

log = logging.getLogger(__name__)

_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)

REPAIR_INSTRUCTION = (
    "Your previous JSON failed schema validation: {error}\n\n"
    "Previous response:\n{previous}\n\n"
    "Regenerate the complete response as valid JSON. Keep the same supported findings, "
    "but correct every invalid value. `confidence` is a probability: use a JSON number "
    "from 0.0 through 1.0 inclusive (for example, 0.85). Never express it as a percentage "
    "and never return a value above 1.0. If you cannot provide a valid confidence, omit "
    "that finding. Return JSON only, with no explanation outside it."
)


class StructuredResult[T: BaseModel](BaseModel):
    value: T | None = None
    error: str | None = None
    calls: int = 0
    """API'ye giden istek sayısı (cache isabetleri sayılmaz)."""
    cached: bool = False
    repaired: bool = False
    usage: Usage = Usage()


class SchemaStats:
    """Şema uyum oranı: ilk denemede geçerli / düzeltmeyle geçerli / başarısız."""

    def __init__(self) -> None:
        self.counts: Counter[str] = Counter()

    def record(self, outcome: str) -> None:
        self.counts[outcome] += 1

    @property
    def total(self) -> int:
        """Modelden gelen yanıt sayısı (cache isabetleri ve API hataları hariç)."""
        return self.counts["valid"] + self.counts["repaired"] + self.counts["invalid"]

    @property
    def compliance_rate(self) -> float:
        """Düzeltme dahil şemaya uyan yanıtların oranı."""
        if not self.total:
            return 1.0
        return (self.counts["valid"] + self.counts["repaired"]) / self.total


def parse_json_output[T: BaseModel](text: str, model_cls: type[T]) -> T:
    """Model çıktısını doğrular; ```json``` çitlerini tolere eder."""
    match = _FENCE.match(text)
    return model_cls.model_validate_json(match.group(1) if match else text)


def _validation_message(exc: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(map(str, e['loc'])) or '<kök>'}: {e['msg']}" for e in exc.errors()[:10]
    )


def _retryable(exc: BaseException) -> bool:
    return isinstance(exc, LLMError) and exc.retryable


class StructuredLLM:
    def __init__(
        self,
        provider: LLMProvider,
        *,
        cache: ResponseCache | None = None,
        max_attempts: int = 3,
        wait: wait_base | None = None,
        stats: SchemaStats | None = None,
    ) -> None:
        self.provider = provider
        self.cache = cache
        self.max_attempts = max_attempts
        self.wait = wait if wait is not None else wait_exponential_jitter(initial=1, max=20)
        self.stats = stats if stats is not None else SchemaStats()

    def _call[T: BaseModel](self, request: LLMRequest, result: StructuredResult[T]) -> LLMResponse:
        """Cache'e bakar; yoksa geçici hatalarda üstel bekleme ile tekrar dener."""
        key = cache_key(self.provider.name, self.provider.model, request)
        if self.cache is not None and (hit := self.cache.get(key)) is not None:
            result.cached = True
            return hit
        retrying = Retrying(
            stop=stop_after_attempt(self.max_attempts),
            wait=self.wait,
            retry=retry_if_exception(_retryable),
            reraise=True,
        )
        for attempt in retrying:
            with attempt:
                result.calls += 1
                response = self.provider.complete(request)
        result.usage = Usage(
            input_tokens=result.usage.input_tokens + response.usage.input_tokens,
            output_tokens=result.usage.output_tokens + response.usage.output_tokens,
        )
        return response

    def _store(self, request: LLMRequest, response: LLMResponse) -> None:
        if self.cache is not None:
            key = cache_key(self.provider.name, self.provider.model, request)
            self.cache.put(key, response)

    def generate[T: BaseModel](
        self, system: str, prompt: str, model_cls: type[T]
    ) -> StructuredResult[T]:
        request = LLMRequest(
            system=system, prompt=prompt, json_schema=model_cls.model_json_schema()
        )
        result: StructuredResult[T] = StructuredResult()
        try:
            response = self._call(request, result)
            try:
                result.value = parse_json_output(response.text, model_cls)
                if not result.cached:
                    self._store(request, response)
                    self.stats.record("valid")
                return result
            except ValidationError as exc:
                error = _validation_message(exc)
                log.info("şemaya uymayan yanıt, düzeltme deneniyor: %s", error)

            repair = request.model_copy(
                update={
                    "prompt": prompt
                    + "\n\n"
                    + REPAIR_INSTRUCTION.format(error=error, previous=response.text)
                }
            )
            repaired = self._call(repair, result)
            try:
                result.value = parse_json_output(repaired.text, model_cls)
            except ValidationError as exc:
                result.error = f"şema doğrulaması başarısız: {_validation_message(exc)}"
                self.stats.record("invalid")
                return result
            # Orijinal isteğin anahtarıyla saklanır: aynı istek tekrar API'ye gitmez.
            self._store(request, repaired)
            result.repaired = True
            self.stats.record("repaired")
        except (LLMError, RetryError) as exc:
            result.error = str(exc)
            self.stats.record("error")
            log.warning("LLM çağrısı başarısız (fail-open): %s", exc)
        finally:
            log.info(
                "şema uyum oranı: %.2f (%s)",
                self.stats.compliance_rate,
                dict(self.stats.counts),
            )
        return result
