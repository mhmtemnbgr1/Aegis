# Yapılacaklar Listesi

Fazlar mantıksal sıradadır. **Faz 1'den itibaren her zaman çalışan, demo yapılabilir bir sistem vardır**; sonraki fazlar onun parçalarını derinleştirir. Görevlerin ayrıntıları ve kabul kriterleri [GitHub Issues](https://github.com/mhmtemnbgr1/Aegis/issues) altında.

## Kapsam (Ekim 2026 revizyonu)

Teslim: **Aralık 2026 sonu**. Proje iki katkıda derinleşir:

- **K1 — ML gatekeeper:** Reponun kendi geçmişinden (SZZ) öğrenilen risk modeli; düşük riskli PR'larda LLM hiç çalışmaz.
- **K2 — Bug-fix hafızası:** Geçmiş hata düzeltmeleri, riskli PR'ı inceleyen yerel LLM'e bağlam olarak verilir.

Kapsam dışı (tezde "gelecek çalışma"): patch ve test üretimi, Docker sandbox, BugsInPy ve RQ3 (eski Faz 5), dashboard, bulut LLM sağlayıcıları. Yalnızca yerel model (Ollama) kullanılır.

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
| 8 | 15 – 21 Ara | Tez metni, sunum provası, yedek video |

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
- [ ] Kendi repomuzda dogfooding (merge sonrası)

## Faz 2 — Repo Madenciliği · 8 Kas

- [x] Miner: PyDriller ile commit, dosya ve fonksiyon değişiklikleri ([şema](docs/mining-schema.md))
- [x] Fix-commit tespiti
- [x] Fix-commit tespiti için 200 örneklik doğrulama seti (precision %71 → %86; LLM önerileriyle tek kişi)
- [x] SZZ (git blame tabanlı MA ve B varyantları; tüm geçmiş) — 50 eşleme kontrol edildi, doğruluk %31
- [x] Kamei JIT metrikleri
- [x] Zaman kuralı: `as_of` ile sızıntısız özellik hesabı
- [x] Sentetik git deposu testleri
- [ ] D1 veri setinin çıkarılması (6 repo, önce tqdm pilotu)
- [ ] *(opsiyonel)* Artımlı madencilik

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
- [ ] `aegis index`
- [ ] Hata kartlarının analiz prompt'una eklenmesi (`memory_refs`)
- [x] Hafıza sinyalinin gatekeeper'a özellik olarak eklenmesi (dar bütçede +4–7 puan)
- [ ] Durum arşivinin Release asset olarak yayınlanması (`aegis publish-state`) ve cache — demo için gerekli
- [ ] *(opsiyonel)* `main` merge'lerinde hafıza ve model güncelleme workflow'u

## ~~Faz 5 — Patch Üretimi ve Doğrulama~~ (v2, kapsam dışı)

Düzeltme ve test ajanları, Docker sandbox, doğrulayıcı, BugsInPy ve suggestion blokları Aralık teslimi için kapsam dışı bırakıldı. Tezde "gelecek çalışma" olarak anılır; ilgili issue'lar `v2` etiketiyle kapatıldı.

## Faz 6 — Değerlendirme · 6 Ara

- [ ] D1, D2 ve D4 veri setlerinin tamamlanması (D2: ~300 + ~300, ~100 elle etiketli)
- [ ] RQ1: ucuz LLM triage taban çizgisi
- [ ] RQ2: hafızasız / plasebo / vektör / hibrit karşılaştırması
- [ ] `aegis eval` ile deneyler
- [ ] İstatistiksel testler, tablolar, grafikler
- [ ] Dogfooding verileri
- [ ] *(opsiyonel)* RQ4: PR-Agent karşılaştırması (aynı yerel model)
- [ ] *(opsiyonel)* RQ5: kör kullanıcı çalışması (6–10 geliştirici)
- [ ] *(opsiyonel)* LLM eğitim verisi kirliliği alt kümesi

## Faz 7 — Sunum ve Tez · 21 Ara

Gereklilikler: [docs/presentation.md](docs/presentation.md)

- [ ] Tez metni
- [ ] Kaynakçanın doğrulanması
- [ ] Demo reposu ve demo PR'ları
- [ ] Canlı demo provası ve yedek video
- [ ] Jüri sorularının sonuç rakamlarıyla güncellenmesi
- [ ] *(opsiyonel)* Veri setinin açık lisansla yayınlanması
- [ ] *(opsiyonel)* Bildiri (UYMS veya benzeri)
