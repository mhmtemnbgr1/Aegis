# Geliştirme Ortamı Kurulumu

## 1. Python ve uv

Python 3.12+ ve [uv](https://docs.astral.sh/uv/) gerekir.

```bash
pip install --user uv          # veya: https://docs.astral.sh/uv/getting-started/installation/
uv sync --all-extras           # proje + Ollama SDK'sı + geliştirme araçları
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

## 3. Ollama ile bug-fix hafızası

Aegis, Ollama'yı sınıflandırıcıyı ince ayar yapmak için değil, geçmiş hata kartlarını yerel
embedding'lerle aramak ve inceleme ajanına benzer örnekleri vermek için kullanır. Sınıflandırıcı
eğitimi LR, RF veya LightGBM ile yapılır.

1. Embedding modelini indirin:

   ```bash
   ollama pull nomic-embed-text
   ```

2. `.aegis.toml` içinde Ollama embedding modelini seçin:

   ```toml
   [memory]
   embedding_model = "ollama:nomic-embed-text"
   ```

3. Madencilik, kart oluşturma, veri kümesi üretimi ve sınıflandırıcı eğitimini sırayla çalıştırın:

   ```bash
   uv run aegis mine https://github.com/owner/repo
   uv run aegis index <yerel-klon-yolu>
   uv run aegis dataset
   uv run aegis train --repo <repo-slug>
   ```

`aegis index`, hata kartlarını ve vektör indeksini üretir. `aegis dataset` komutunu bundan sonra
çalıştırmak, `mem_func_bugs` ve `mem_file_bugs` hafıza özelliklerini D1'e ekler. Repo slug'ı
madencilik çıktısında gösterilir. Bu akış Qwen'in ağırlıklarını değiştirmez; Ollama'da çalıştırmak
üzere ayrı bir ince ayar adapter'ı üretmez.

## 4. Gerçek modelle injection testleri (isteğe bağlı)

CI bu testleri mock LLM ile koşar. Gerçek modelle elle denemek için:

```bash
AEGIS_LIVE_PROVIDER=ollama AEGIS_LIVE_MODEL=qwen2.5-coder:7b uv run pytest -m live
```

## 5. GitHub Action'da LLM

GitHub'ın barındırılan runner'larında Ollama yoktur. LLM analizini Action'da açmak için Ollama'nın
erişilebilir olduğu bir ortam gerekir (ör. Ollama kurulu self-hosted runner). Adresi action'ın
`ollama-host` girdisiyle verin ve `.github/aegis.toml` içinde `llm_enabled = true` yapın. Aksi
halde Action yalnızca gatekeeper ve deterministik kurallarla çalışır.
