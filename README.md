# 🛡️ Aegis

**Risk odaklı, hafızalı ve çok ajanlı PR inceleme sistemi.**

Aegis bir Pull Request açıldığında üç adımda çalışır:

1. Değişikliğin riskini **klasik bir ML modeliyle** ölçer ve düşük riskli PR'ları LLM'e hiç göndermez.
2. Riskli PR'ları incelerken LLM'e **reponun kendi geçmiş hatalarını** hatırlatır.
3. Bulguları diff'e karşı doğrular ve PR'a yorum olarak yazar; PR'ı asla bloklamaz. Tüm modeller **yerelde** (Ollama) çalışır, kod dışarı çıkmaz.

> **Durum:** Geliştirme aşaması · **Hedef dil:** Python · **Teslim şekli:** GitHub Action + CLI

---

## Neden?

| Mevcut yaklaşım | Eksik kalan | Aegis'in cevabı |
| --- | --- | --- |
| LLM PR botları (PR-Agent, CodeRabbit, Copilot review) | Her PR'a LLM çağırır; repo geçmişini bilmez; kodu buluta gönderir | **Gatekeeper** düşük riskli PR'ları eler · **Bug-fix hafızası** geçmişi hatırlatır · **Yerel model** kodu dışarı çıkarmaz |
| JIT hata tahmini (SZZ + Git metrikleri + RF/XGBoost) | "%75 hatalı" der ama hatanın ne olduğunu söylemez, düzeltme önermez | Tahmin sonucunu LLM için bir **maliyet kapısı** olarak kullanır ve bir **aksiyona** dönüştürür |

## Nasıl Çalışır?

```mermaid
flowchart LR
    PR[PR açıldı] --> GK{Gatekeeper<br/>risk skoru}
    GK -- düşük --> S[Özet yorumu<br/>LLM yok]
    GK -- orta / yüksek --> MEM[Bug-fix hafızası<br/>geçmiş hata kartları]
    MEM --> AN[Analiz ajanı<br/>yerel LLM]
    AN --> F[Kanıt + satır<br/>doğrulama]
    F --> PUB[PR yorumu]
```

PR'da çıkan sonuç şöyle görünür:

> **🛡️ Aegis — Risk: 0.82 (yüksek)**
> Neden: bu fonksiyonda geçmişte 2 hata düzeltilmiş · 3 alt sisteme yayılan değişiklik
> Hafıza: `BC-0142` (#89, bağlantı havuzu sızıntısı)
> Sonuç: 1 bulgu · 4.120 token

## Fazlar

| Faz | İçerik | Sonuç |
| --- | --- | --- |
| 0 | Altyapı | CI, tip kontrolü, geliştirme ortamı |
| 1 | **Uçtan uca iskelet** | Sezgisel gatekeeper + tek LLM çağrısı + PR yorumu. İlk günden demo yapılabilir. |
| 2 | Repo madenciliği | PyDriller, fix-commit tespiti, SZZ, JIT metrikleri |
| 3 | ML Gatekeeper | Sezgisel kuralın yerine eğitilmiş, açıklanabilir risk modeli gelir |
| 4 | Bug-fix hafızası | Hata kartları, hibrit arama, analiz ajanına bağlam |
| ~~5~~ | ~~Patch ve doğrulama~~ | Kapsam dışı (v2): tezde gelecek çalışma |
| 6 | Değerlendirme | RQ1 (gatekeeper) ve RQ2 (hafıza) ablation deneyleri |
| 7 | Sunum ve tez | [docs/presentation.md](docs/presentation.md) |

Her faz bir önceki fazın çalışan sistemini derinleştirir. Teslim Aralık 2026 sonu; haftalık takvim ve kesme çizgileri [TODO.md](TODO.md) içinde. Ayrıntılı görevler [TODO.md](TODO.md) dosyasında ve [GitHub Issues](https://github.com/mhmtemnbgr1/Aegis/issues) altında.

## Kullanım

### Yerelde

```bash
aegis score  --base main          # yalnızca risk skoru
aegis review --base main          # gatekeeper + analiz ajanı; sonuç terminale
aegis review --base main --no-llm # LLM'siz, yalnızca deterministik kurallar
```

Eğitilmiş risk modeli (Faz 2–3):

```bash
aegis mine .                      # geçmişi tara, fix'leri bul, SZZ ve Kamei metrikleri
aegis dataset                     # taranan repolardan D1
aegis train --repo <slug>         # LR / RF / LightGBM; kalibre, zaman sıralı
aegis score main..HEAD --model .aegis/models/<slug>/lr-none.pkl   # skor, bant, açıklama
```

`[gatekeeper] mode = "model"` ile `aegis score` modeli kendisi bulur; model ya da madencilik geçmişi yoksa sezgisel kurala döner.

Bug-fix hafızası (Faz 4):

```bash
aegis index .                     # fix commit'lerinden hata kartları (artımlı)
```

Planlanan (Faz 4): embedding ve hibrit arama, `aegis publish-state`.

### GitHub Action

`.github/workflows/aegis.yml`:

```yaml
name: Aegis
on:
  pull_request:            # pull_request_target KULLANMAYIN

permissions:
  contents: read
  pull-requests: write     # özet ve satır yorumları
  checks: write            # check run

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # base...head diff'i için tam geçmiş
      - uses: mhmtemnbgr1/Aegis@main
        with:
          ollama-host: ${{ vars.OLLAMA_HOST }}   # Ollama'lı self-hosted runner / sunucu
```

- Yapılandırma (`.aegis.toml`) ve `.aegisignore` **taban dalın** sürümünden okunur; PR kendi incelemesini gevşetemez.
- Yalnızca **yerel model (Ollama)** kullanılır; bulut LLM'i ve API anahtarı yoktur. `ollama-host` verilmezse (GitHub'ın barındırılan runner'larında Ollama yoktur) LLM adımı uyarısız atlanır ve inceleme gatekeeper ile deterministik kurallarla sürer.
- Aegis PR'ı **asla bloklamaz**: kendi hatasında check run `neutral` olur ve özet yorumunda uyarı bırakılır.
- Her çalıştırmanın metrikleri `aegis-runs-*` artifact'ı olarak yüklenir.

Tüm seçenekler: [`action.yml`](action.yml) · [`.aegis.toml.example`](.aegis.toml.example)

## Dokümanlar

| Dosya | İçerik |
| --- | --- |
| [docs/rad.md](docs/rad.md) | Gereksinim Analiz Dokümanı (RAD): kapsam, hedefler, FR/NFR, senaryolar, UML modelleri, arayüz taslakları |
| [docs/setup.md](docs/setup.md) | Geliştirme ortamı: uv, Ollama |
| [docs/architecture.md](docs/architecture.md) | Gereksinimler, katman ayrıntıları, şemalar, modüller, teknoloji yığını, güvenlik |
| [docs/presentation.md](docs/presentation.md) | Sunum ve tez: katkılar, araştırma soruları, değerlendirme planı, demo, jüri soruları |
| [docs/target-repos.md](docs/target-repos.md) | Eğitim ve değerlendirmede kullanılan repolar |
| [docs/ideas.md](docs/ideas.md) | Kapsam dışı fikirler |

## Geliştirme

```bash
uv sync --all-extras        # Ollama SDK'sı dahil
uv run pre-commit install   # commit öncesi ruff, ruff-format, mypy
uv run ruff check .
uv run mypy
uv run pytest
```

## Lisans

[MIT](LICENSE)
