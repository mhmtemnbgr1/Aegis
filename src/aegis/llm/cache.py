"""Hash tabanlı, dosya sistemi üzerinde yanıt cache'i.

Anahtar; sağlayıcı, model ve isteğin tamamından (sistem prompt'u, kullanıcı prompt'u, şema,
`max_tokens`) üretilir. Aynı istek ikinci kez API'ye gitmez.
"""

import hashlib
import json
from pathlib import Path

from pydantic import ValidationError

from aegis.llm.base import LLMRequest, LLMResponse

DEFAULT_CACHE_DIR = Path(".aegis") / "cache" / "llm"


def cache_key(provider: str, model: str, request: LLMRequest) -> str:
    payload = json.dumps(
        {"provider": provider, "model": model, "request": request.model_dump(mode="json")},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ResponseCache:
    def __init__(self, directory: Path | str = DEFAULT_CACHE_DIR) -> None:
        self.directory = Path(directory)

    def _path(self, key: str) -> Path:
        return self.directory / key[:2] / f"{key}.json"

    def get(self, key: str) -> LLMResponse | None:
        path = self._path(key)
        if not path.is_file():
            return None
        try:
            return LLMResponse.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError):
            return None  # bozuk kayıt: cache ıskası gibi davran

    def put(self, key: str, response: LLMResponse) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(response.model_dump_json(), encoding="utf-8")
        tmp.replace(path)
