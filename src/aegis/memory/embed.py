"""Hata kartları ve sorgular için embedding (#24).

Embedding modeli `[memory].embedding_model` ile seçilir; hepsi aynı `Embedder` arayüzünü uygular:

- `lsa` (varsayılan): TF-IDF + kesik SVD (latent semantic analysis), scikit-learn ile. Ek
  bağımlılık, model indirmesi ya da internet gerektirmez; kartlar üzerinde eğitilir ve CPU'da
  saniyeler sürer. Kod için ayarlanmış belirteçleme: `snake_case` ve `camelCase` adlar parçalanır.
- `ollama:<model>` (ör. `ollama:nomic-embed-text`): yerel Ollama sunucusundaki bir embedding
  modeli (`uv sync --extra ollama`). Gerçek model koşuları proje sonunda yapılacağı için bu
  makinede denenmedi; arayüz birim testleriyle doğrulanır.

Plandaki sentence-transformers + LanceDB, bu ortamda torch ve pyarrow kurulamadığı için
kullanılmadı; birkaç bin kart için tam tarama zaten milisaniyeler sürer (bkz. `index`).
Vektörler L2 normalize edilir; benzerlik iç çarpımdır (kosinüs).
"""

import re
from typing import Any, Protocol

import numpy as np
from numpy.typing import NDArray

Matrix = NDArray[np.float32]

_SPLIT_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_]+")


def code_tokens(text: str) -> list[str]:
    """Kod duyarlı belirteçler.

    `release_conn` → release, conn, release_conn; `getAttr` → get, attr, getattr.
    """
    out: list[str] = []
    for word in _TOKEN.findall(text):
        parts = [p for chunk in word.split("_") for p in _SPLIT_CAMEL.split(chunk) if p]
        lowered = [p.lower() for p in parts if len(p) > 1]
        out += lowered
        if len(lowered) > 1:
            out.append(word.lower())
    return out


def _normalize(x: NDArray[Any]) -> Matrix:
    x = np.asarray(x, dtype=np.float32)
    norms = np.linalg.norm(x, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    out: Matrix = x / norms
    return out


class Embedder(Protocol):
    name: str

    def fit(self, texts: list[str]) -> "Embedder":
        """Kart metinleri üzerinde hazırlık (LSA eğitilir; önceden eğitilmiş modellerde boş)."""
        ...

    def encode(self, texts: list[str]) -> Matrix:
        """L2 normalize vektörler (satır başına bir metin)."""
        ...


class LsaEmbedder:
    def __init__(self, dims: int = 256, seed: int = 0) -> None:
        self.name = "lsa"
        self.dims = dims
        self.seed = seed
        self._vectorizer: Any = None
        self._svd: Any = None

    def fit(self, texts: list[str]) -> "LsaEmbedder":
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer

        self._vectorizer = TfidfVectorizer(
            tokenizer=code_tokens,
            token_pattern=None,
            lowercase=False,
            sublinear_tf=True,
            min_df=1,
            # Çok yaygın belirteçler (ör. self, return) ayırt edici değil; küçük setlerde
            # bu eşik tüm sözlüğü silebileceği için yalnızca yeterli kartta uygulanır.
            max_df=0.5 if len(texts) >= 10 else 1.0,
        )
        tfidf = self._vectorizer.fit_transform(texts)
        k = min(self.dims, tfidf.shape[0] - 1, tfidf.shape[1] - 1)
        # Çok küçük setlerde SVD anlamsız: TF-IDF vektörleri doğrudan kullanılır.
        self._svd = (
            TruncatedSVD(n_components=k, random_state=self.seed).fit(tfidf) if k >= 2 else None
        )
        return self

    def encode(self, texts: list[str]) -> Matrix:
        if self._vectorizer is None:
            raise RuntimeError("LSA eğitilmedi; önce fit()")
        tfidf = self._vectorizer.transform(texts)
        return _normalize(self._svd.transform(tfidf) if self._svd is not None else tfidf.toarray())


class OllamaEmbedder:
    """Yerel Ollama sunucusundaki embedding modeli (`OLLAMA_HOST`)."""

    def __init__(self, model: str, client: Any = None, batch: int = 32) -> None:
        self.name = f"ollama:{model}"
        self.model = model
        self.batch = batch
        self._client = client

    def fit(self, texts: list[str]) -> "OllamaEmbedder":
        return self

    def encode(self, texts: list[str]) -> Matrix:
        if self._client is None:
            import ollama  # isteğe bağlı bağımlılık: uv sync --extra ollama

            self._client = ollama.Client()
        rows: list[list[float]] = []
        for i in range(0, len(texts), self.batch):
            response = self._client.embed(model=self.model, input=texts[i : i + self.batch])
            rows += list(response["embeddings"])
        return _normalize(np.array(rows))

    def __getstate__(self) -> dict[str, Any]:
        # İstemci (ağ bağlantısı) diske yazılmaz; yüklendiğinde yeniden kurulur.
        return {**self.__dict__, "_client": None}


def create_embedder(spec: str) -> Embedder:
    """`lsa` (ya da eski `local`), `lsa:<boyut>` veya `ollama:<model>`."""
    kind, _, arg = spec.partition(":")
    if kind in ("lsa", "local"):
        return LsaEmbedder(dims=int(arg) if arg else 256)
    if kind == "ollama" and arg:
        return OllamaEmbedder(arg)
    raise ValueError(f"bilinmeyen embedding modeli: {spec!r} (lsa, lsa:<boyut>, ollama:<model>)")
