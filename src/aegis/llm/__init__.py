"""LLM sağlayıcıları: tek protokol, dört adaptör (FR-37)."""

from aegis.config import AgentConfig
from aegis.llm.base import LLMError, LLMProvider, LLMRequest, LLMResponse, Usage
from aegis.llm.providers import (
    AnthropicProvider,
    GeminiProvider,
    MockProvider,
    OllamaProvider,
    OpenAIProvider,
)


def create_provider(config: AgentConfig) -> LLMProvider:
    """Ajan ayarından sağlayıcı oluşturur."""
    timeout = config.timeout_seconds
    match config.provider:
        case "ollama":
            return OllamaProvider(config.model, temperature=config.temperature, timeout=timeout)
        case "gemini":
            return GeminiProvider(config.model, temperature=config.temperature, timeout=timeout)
        case "openai":
            return OpenAIProvider(config.model, temperature=config.temperature, timeout=timeout)
        case "anthropic":
            return AnthropicProvider(config.model, effort=config.effort, timeout=timeout)


__all__ = [
    "AnthropicProvider",
    "GeminiProvider",
    "LLMError",
    "LLMProvider",
    "LLMRequest",
    "LLMResponse",
    "MockProvider",
    "OllamaProvider",
    "OpenAIProvider",
    "Usage",
    "create_provider",
]
