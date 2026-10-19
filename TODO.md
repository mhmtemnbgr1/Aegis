# Yapılacaklar Listesi

> Ayrıntılı açıklamalar için [README](README.md#8-faz-faz-geliştirme-planı) dosyasına bakın. Tamamlanan maddeler `[x]` ile işaretlenir.

## Faz 0 — Hazırlık ve İskelet (1. hafta)

- [x] Depo yapısı, `pyproject.toml`, `uv` ortamı
- [x] GitHub Actions CI, issue/PR şablonları
- [x] `aegis --version` komutu
- [ ] mypy ve pre-commit kurulumu
- [x] Hedef repoların seçimi: black, fastapi, httpie, scrapy, tornado, tqdm ([docs/target-repos.md](docs/target-repos.md))
- [ ] Her ekip üyesi için Ollama kurulumu ve Gemini API anahtarı
- [ ] GitHub Projects panosunun kurulması

## Faz 1 — Repo Madenciliği ve Veri Hattı (2.–3. hafta)

- [ ] `aegis mine`: PyDriller ile commit, dosya ve fonksiyon değişikliklerini Parquet'e yazma
- [ ] Fix-commit tespiti (mesaj kalıpları + issue etiketleri)
- [ ] Fix-commit tespiti için 200 örneklik elle etiketlenmiş doğrulama seti
- [ ] SZZ: boşluk/yorum filtreleme, merge ve büyük commit eleme
- [ ] Kamei JIT metrikleri (NS, ND, NF, Entropy, LA, LD, LT, FIX, NDEV, AGE, NUC, EXP, REXP, SEXP)
- [ ] Artımlı madencilik
- [ ] SZZ ve metrikler için sentetik git deposu testleri
- [ ] Seçilen repolardan D1 veri setinin çıkarılması

## Faz 2 — ML Gatekeeper (4.–5. hafta)

- [ ] Zaman sıralı veri bölme ve etiket gecikmesi tamponu
- [ ] Lojistik regresyon, Random Forest ve LightGBM modelleri
- [ ] Sınıf dengesizliği yöntemlerinin karşılaştırılması
- [ ] Repo içi ve repolar arası (cross-project) değerlendirme
- [ ] Kalibrasyon, bütçe tabanlı eşik seçimi, risk bantları (düşük / orta / yüksek)
- [ ] SHAP açıklamaları
- [ ] `aegis train` ve `aegis score <base>..<head>` komutları
- [ ] RQ1 ilk sonuçları: bütçe–recall eğrisi

## Faz 3 — Bug-Fix Hafızası (6.–7. hafta)

- [ ] Hata kartı (BugCard) modeli ve oluşturucu
- [ ] Fonksiyon düzeyinde parçalama (`ast`)
- [ ] Yerel embedding modeli ve LanceDB indeksi
- [ ] Hibrit arama: yapısal + BM25 + vektör, RRF ile birleştirme
- [ ] Zamansal filtre (yalnızca PR tarihinden önceki kartlar)
- [ ] Getirme değerlendirmesi (Recall@k, MRR)
- [ ] `aegis index` komutu ve artımlı güncelleme
- [ ] Hafıza sinyalinin gatekeeper'a özellik olarak eklenmesi

## Faz 4 — LLM Katmanı ve Analiz Ajanı (8.–9. hafta)

- [ ] `LLMProvider` protokolü
- [ ] Ollama, Gemini, OpenAI ve Anthropic adaptörleri
- [ ] Structured output, retry, yanıt cache'i
- [ ] Analiz ajanı prompt'ları (versiyonlu, few-shot, "neleri raporlama" listesi)
- [ ] Hata kartlarının prompt'a eklenmesi ve `memory_refs` atfı
- [ ] Kanıt (`evidence`) ve satır doğrulama filtreleri
- [ ] `aegis review --base main` ile yerelde uçtan uca inceleme
- [ ] RQ2 deneyi: hafızasız, yalnızca vektör ve hibrit hafıza karşılaştırması

## Faz 5 — Düzeltme ve Test Ajanları, Doğrulayıcı (10.–11. hafta)

- [ ] Düzeltme ajanı (minimal unified diff)
- [ ] Test ajanı (hatayı yeniden üreten pytest testi)
- [ ] Docker sandbox (ağ kapalı, CPU/bellek/süre sınırlı)
- [ ] Doğrulayıcı: apply → lint → mevcut testler → üretilen test (önce/sonra) → statü
- [ ] Geri besleme döngüsü (en fazla 2 tekrar)
- [ ] Orkestratör durum makinesi ve birim testleri
- [ ] RQ3 deneyi: BugsInPy alt kümesinde tek çağrı ile çok ajanlı zincirin karşılaştırması

## Faz 6 — GitHub Action ve Yayıncı (12. hafta)

- [ ] `action.yml` (composite action)
- [ ] Model ve indeksin `actions/cache` ile taşınması
- [ ] Özet yorumu (oluşturma ve güncelleme)
- [ ] Satır yorumları ve ` ```suggestion ` blokları
- [ ] Suggestion aralığının diff hunk'ına sığma kontrolü ve yedek biçim
- [ ] Fail-open davranışı, check run sonucu (`neutral` / `success`)
- [ ] `main` merge'lerinde hafıza ve model güncelleme workflow'u
- [ ] Fork PR güvenliği (`pull_request_target` yok, sandbox'ta anahtar yok)
- [ ] Demo reposu ve kendi depomuzda kullanım (dogfooding)

## Faz 7 — Değerlendirme (13. hafta)

- [ ] D1–D4 veri setlerinin tamamlanması
- [ ] Tüm deneylerin son konfigürasyonlarla koşturulması (`aegis eval`)
- [ ] İstatistiksel testler (Wilcoxon, McNemar)
- [ ] Tablolar ve grafikler (`eval/reports/`)
- [ ] Patch'lerin elle doğruluk incelemesi (iki kişi, uyuşma oranı)
- [ ] LLM eğitim verisi kirliliği için bilgi kesim tarihi sonrası alt küme
- [ ] Dogfooding verileri: PR başına süre, maliyet, 👍/👎

## Faz 8 — Tez Yazımı ve Jüri Demosu (14. hafta)

- [ ] Tez metni: problem, ilgili çalışmalar, mimari, RQ1–RQ4 sonuçları, geçerlilik tehditleri
- [ ] Kaynakçanın doğrulanması ve genişletilmesi
- [ ] Canlı demo senaryosu (~5 dk)
- [ ] Kayıtlı yedek demo videosu
- [ ] `docs/jury-faq.md` güncellemesi
