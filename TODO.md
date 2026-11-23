# Yapılacaklar Listesi

Fazlar mantıksal sıradadır. **Faz 1'den itibaren her zaman çalışan, demo yapılabilir bir sistem vardır**; sonraki fazlar onun parçalarını derinleştirir. Görevlerin ayrıntıları ve kabul kriterleri [GitHub Issues](https://github.com/mhmtemnbgr1/Aegis/issues) altında.

## Kapsam (Ekim 2026 revizyonu)

Proje iki katkıda derinleşir:

- **K1 — ML gatekeeper:** Reponun kendi geçmişinden (SZZ) öğrenilen risk modeli; düşük riskli PR'larda LLM hiç çalışmaz.
- **K2 — Bug-fix hafızası:** Geçmiş hata düzeltmeleri, riskli PR'ı inceleyen yerel LLM'e bağlam olarak verilir.

Kapsam dışı (gelecek çalışma): patch ve test üretimi, Docker sandbox, BugsInPy ve RQ3 (eski Faz 5), dashboard, bulut LLM sağlayıcıları. Yalnızca yerel model (Ollama) kullanılır.

GitHub'da `opsiyonel` etiketli işler zaman kalırsa yapılır; `v2` etiketli işler kapatıldı.

## Takvim

| Hafta | Tarih | Hedef |
| --- | --- | --- |
| 1 | 27 Eki – 2 Kas | Faz 1 PR'ının merge'i; miner, fix-commit tespiti, SZZ (tqdm pilotu) |
| 2 | 3 – 9 Kas | Kamei metrikleri, `as_of` kuralı, D1 (6 repo), 200 örneklik doğrulama |
| 3 | 10 – 16 Kas | ML gatekeeper: modeller, zaman sıralı bölme, kalibrasyon, SHAP, `aegis train/score` |
| 4 | 17 – 23 Kas | Hafıza: hata kartları, parçalama, LanceDB, hibrit arama, zaman filtresi |
| 5 | 24 – 30 Kas | Gerçek Ollama koşuları, RQ1 deneyi |
| 6 | 1 – 7 Ara | RQ2 deneyi (hafızasız / plasebo / vektör / hibrit), istatistik |
| 7 | 8 – 14 Ara | Demo reposu, dogfooding verisi; zaman kalırsa RQ4 |
| 8 | 15 – 21 Ara | Belgeler, sunum provası, yedek video |

## Kesme Çizgileri

Geride kalınırsa önceden kararlaştırılmış sırayla kesilir:

1. `opsiyonel` işler: RQ4 (PR-Agent), RQ5 (kullanıcı çalışması), bildiri, veri seti yayını, artımlı güncelleme workflow'u.
2. Hafızada yalnızca yapısal + vektör arama kalır; BM25 ve RRF çıkarılır.
3. Repolar arası değerlendirme 6 yerine 3 repoyla yapılır.

Faz 2–4, RQ1 ve RQ2 kesilmez.

---

## Faz 0 — Altyapı · 31 Eki

- [x] Depo yapısı, `pyproject.toml`, `uv` ortamı
- [x] GitHub Actions CI, issue/PR şablonları
- [x] `aegis --version` komutu
- [x] Hedef repoların seçimi ([docs/target-repos.md](docs/target-repos.md))
- [x] mypy ve pre-commit
- [ ] Geliştirme ortamı: Ollama ([docs/setup.md](docs/setup.md) hazır)
- [ ] GitHub Projects panosu ve branch koruması
- [ ] Görev dağılımı
- [ ] Proje yönünün ve kapsam revizyonunun danışmana onaylatılması

## Faz 1 — Uçtan Uca İskelet · 31 Eki

Amaç: En basit haliyle bütün hattı çalıştırmak: PR → risk → LLM → PR yorumu.

- [x] Diff ayrıştırma ve ön filtre (binary, lock, üretilmiş dosyalar)
- [x] Sezgisel gatekeeper (değişen satır + riskli yol); deneylerde taban çizgisi olarak da kullanılır
- [x] `LLMProvider` protokolü ve yerel Ollama adaptörü
- [x] Structured output, retry ve yanıt cache'i
- [x] Analiz ajanı prompt'ları (versiyonlu)
- [x] Kanıt ve satır doğrulama filtreleri
- [x] Prompt injection önlemleri ve saldırı testleri
- [x] `aegis review --base main`
- [x] `action.yml` (composite action)
- [x] Özet yorumu (oluştur / güncelle)
- [x] Bulguların satır yorumu olarak yayınlanması
- [x] Fail-open ve check run sonucu
- [x] Kendi repomuzda dogfooding (Aegis Action her PR'da çalışıyor)

## Faz 2 — Repo Madenciliği · 8 Kas

- [x] Miner: PyDriller ile commit, dosya ve fonksiyon değişiklikleri ([şema](docs/mining-schema.md))
- [x] Fix-commit tespiti
- [x] Fix-commit tespiti için 200 örneklik doğrulama seti (precision %71 → %86; LLM önerileriyle tek kişi)
- [x] SZZ (git blame tabanlı MA ve B varyantları; tüm geçmiş) — 50 eşleme kontrol edildi, doğruluk %31
- [x] Kamei JIT metrikleri
- [x] Zaman kuralı: `as_of` ile sızıntısız özellik hesabı
- [x] Sentetik git deposu testleri
- [x] D1 veri setinin çıkarılması (6 repo; eşik altı fastapi ve httpie yerine luigi ve sanic, #95)
- [x] SZZ süzgeçleri denendi (issue, taşıma, tarih): bu veride doğruluğu artırmadı ([mining-schema](docs/mining-schema.md))
- [x] *(opsiyonel)* Artımlı madencilik (#94)

## Faz 3 — ML Gatekeeper · 15 Kas

- [x] Zaman sıralı bölme ve etiket gecikmesi tamponu
- [x] LR, Random Forest ve LightGBM (`aegis train`)
- [x] Sınıf dengesizliği yöntemleri
- [x] Repo içi ve repolar arası değerlendirme
- [x] PR düzeyinde etiket ve özellikler
- [x] Kalibrasyon, bütçe tabanlı eşik, risk bantları
- [x] SHAP açıklamaları
- [x] `aegis train` ve `aegis score`
- [x] Sezgisel gatekeeper'ın eğitilmiş modelle değiştirilmesi
- [x] Maliyet–recall eğrisi ve iki işletme noktası (ilk sonuçlar)

## Faz 4 — Bug-Fix Hafızası · 22 Kas

- [x] Hata kartı modeli ve oluşturucu
- [x] Fonksiyon düzeyinde parçalama
- [x] Embedding ve vektör indeksi (LSA + numpy; Ollama isteğe bağlı)
- [x] Hibrit arama (yapısal + BM25 + vektör, RRF)
- [x] Zamansal filtre
- [x] Getirme değerlendirmesi (Recall@k, MRR) — hibrit MRR 0,582
- [x] `aegis index` (artımlı kartlar, sürümlü indeks)
- [x] Hata kartlarının analiz prompt'una eklenmesi (`memory_refs`; prompt v2)
- [x] Hafıza sinyalinin gatekeeper'a özellik olarak eklenmesi (dar bütçede +4–7 puan)
- [x] Durum arşivinin Release asset olarak yayınlanması (`aegis publish-state`) ve cache — demo için gerekli
- [x] *(opsiyonel)* `main` merge'lerinde hafıza ve model güncelleme workflow'u (#97)

## ~~Faz 5 — Patch Üretimi ve Doğrulama~~ (v2, kapsam dışı)

Düzeltme ve test ajanları, Docker sandbox, doğrulayıcı, BugsInPy ve suggestion blokları kapsam dışı bırakıldı; "gelecek çalışma" olarak kalır; ilgili issue'lar `v2` etiketiyle kapatıldı.

## Faz 6 — Değerlendirme · 6 Ara

- [ ] D1, D2 ve D4 veri setlerinin tamamlanması — D2 (300 + 300) hazır; revert seti için 102 örneklik yeni insan incelemesi hazırlanıyor (eski SZZ etiketleri ayrı tutuluyor, [yönerge](eval/d2-etiketleme.md)); D4'te 54 çalıştırma / 28 PR var, hedef ≥30
- [ ] RQ1: ucuz LLM triage taban çizgisi — betik ve 1.250 PR'lık örneklem hazır, Ollama koşusu bekliyor ([kılavuz](docs/llm-experiments.md))
- [ ] RQ2: hafızasız / plasebo / vektör / hibrit karşılaştırması — betik, D2 ve hafıza hazırlığı hazır, Ollama koşusu bekliyor
- [ ] Deneylerin tek komutla koşturulması — `eval/rq2.py` ve `eval/rq1_triage.py` (kuru koşu, kaldığı yerden devam)
- [ ] İstatistiksel testler, tablolar, grafikler — LLM'siz kısım hazır (`docs/results.md`); LLM deneyleri bekliyor
- [ ] Dogfooding verileri
- [ ] *(opsiyonel)* RQ4: PR-Agent karşılaştırması (aynı yerel model)
- [ ] *(opsiyonel)* RQ5: kör kullanıcı çalışması (6–10 geliştirici)
- [ ] *(opsiyonel)* LLM eğitim verisi kirliliği alt kümesi — tanımlandı (`after_cutoff`), D2'de yalnızca 17 örnek

## Faz 7 — Sunum ve Belgeler · 21 Ara

Gereklilikler: [docs/presentation.md](docs/presentation.md)

- [x] Kaynakçanın doğrulanması (künyeler yayıncı sayfalarıyla kontrol edildi, kullanılan yöntemler eklendi)
- [x] Demo reposu ve demo PR'ları — fork'ta canlı çalışıyor (LLM'siz yorumlar); LLM bulguları yerel çalıştırmada (#98)
- [ ] Canlı demo provası ve yedek video
- [ ] Sık sorulan soruların sonuç rakamlarıyla güncellenmesi — LLM'siz rakamlar eklendi; LLM deneyleri bekliyor
- [ ] *(opsiyonel)* Veri setinin açık lisansla yayınlanması
- [ ] *(opsiyonel)* Bildiri (UYMS veya benzeri)
