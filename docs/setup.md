# Geliştirme Ortamı Kurulumu

## 1. Python ve uv

Python 3.12+ ve [uv](https://docs.astral.sh/uv/) gerekir.

```bash
pip install --user uv          # veya: https://docs.astral.sh/uv/getting-started/installation/
uv sync --all-extras           # proje + tüm LLM SDK'ları + geliştirme araçları
uv run pre-commit install      # commit öncesi ruff, ruff-format, mypy
```

Kontrol:

```bash
uv run ruff check .
uv run mypy
uv run pytest
uv run aegis review --base main --no-llm
```

> **Windows — Akıllı Uygulama Denetimi (Smart App Control):** Bu ilke açıksa mypy'nin derlenmiş
> modülleri (`librt`, mypyc) "Uygulama Denetimi ilkesi bu dosyayı engelledi" hatasıyla
> yüklenemeyebilir. Geçici çözüm olarak saf Python bir mypy kurun:
>
> ```bash
> MYPY_USE_MYPYC=0 uv pip install --no-binary mypy "mypy==1.18.2"
> .venv/Scripts/python -m mypy
> ```
>
> `uv sync` bu sürümü tekrar değiştirir; CI her zaman `uv.lock`'taki sürümü kullanır.

## 2. Yerel model: Ollama

1. [ollama.com](https://ollama.com/download) adresinden Ollama'yı kurun.
2. Modeli indirin ve deneyin:

   ```bash
   ollama pull qwen2.5-coder:7b
   ollama run qwen2.5-coder:7b "merhaba"
   ```

3. Ollama farklı bir adreste çalışıyorsa `OLLAMA_HOST` ortam değişkenini ayarlayın
   (varsayılan `http://localhost:11434`).

`.aegis.toml` içinde varsayılan analiz modeli zaten budur:

```toml
[agents.analyst]
provider = "ollama"
model = "qwen2.5-coder:7b"
```

## 3. Gemini API anahtarı (ücretsiz kota)

1. [Google AI Studio](https://aistudio.google.com/apikey) üzerinden bir anahtar oluşturun.
2. Anahtarı **yalnızca ortam değişkeni olarak** tanımlayın; hiçbir dosyaya yazmayın:

   ```bash
   # bash / zsh (~/.bashrc veya ~/.zshrc)
   export GEMINI_API_KEY="..."
   ```

   ```powershell
   # PowerShell (kalıcı, kullanıcı düzeyi)
   [Environment]::SetEnvironmentVariable("GEMINI_API_KEY", "...", "User")
   ```

3. Gemini ile denemek için `.aegis.toml`:

   ```toml
   [agents.analyst]
   provider = "gemini"
   model = "gemini-flash-latest"
   ```

## 4. Gerçek modelle injection testleri (isteğe bağlı)

CI bu testleri mock LLM ile koşar. Gerçek modelle elle denemek için:

```bash
AEGIS_LIVE_PROVIDER=ollama AEGIS_LIVE_MODEL=qwen2.5-coder:7b uv run pytest -m live
```

## 5. GitHub Action için gizli anahtar

Repo ayarlarında **Settings → Secrets and variables → Actions → New repository secret**:
`GEMINI_API_KEY`. Dogfooding workflow'u (`.github/workflows/aegis.yml`) bu anahtarı kullanır;
LLM'i açmak için `.github/aegis.toml` içinde `llm_enabled = true` yapın.
