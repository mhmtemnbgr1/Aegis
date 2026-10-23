"""LLM sağlayıcıları: tek protokol; yerel Ollama adaptörü ve testler için Mock (FR-37)."""

from aegis.config import AgentConfig
from aegis.llm.base import LLMError, LLMProvider, LLMRequest, LLMResponse, Usage
from aegis.llm.cache import ResponseCache
from aegis.llm.providers import MockProvider, OllamaProvider
from aegis.llm.structured import SchemaStats, StructuredLLM, StructuredResult


def create_provider(config: AgentConfig) -> LLMProvider:
    """Ajan ayarından sağlayıcı oluşturur."""
    return OllamaProvider(
        config.model, temperature=config.temperature, timeout=config.timeout_seconds
    )


__all__ = [
    "LLMError",
    "LLMProvider",
    "LLMRequest",
    "LLMResponse",
    "MockProvider",
    "OllamaProvider",
    "ResponseCache",
    "SchemaStats",
    "StructuredLLM",
    "StructuredResult",
    "Usage",
    "create_provider",
]
