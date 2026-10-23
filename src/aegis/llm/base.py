"""Sağlayıcıdan bağımsız LLM arayüzü (FR-37, NFR-07)."""

from typing import Any, Protocol

from pydantic import BaseModel, Field


class LLMError(RuntimeError):
    """Sağlayıcı çağrısı başarısız oldu (ağ, kota, ret, boş yanıt...)."""


class LLMRequest(BaseModel):
    system: str
    prompt: str
    json_schema: dict[str, Any] | None = None
    """Verilirse sağlayıcının yapılandırılmış çıktı özelliği bu şemayla kullanılır."""
    max_tokens: int = Field(default=4096, gt=0)


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class LLMResponse(BaseModel):
    text: str
    provider: str
    model: str
    usage: Usage = Usage()


class LLMProvider(Protocol):
    name: str
    model: str

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Tek bir istek gönderir; hata durumunda `LLMError` fırlatır."""
        ...
