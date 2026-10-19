# Yapılacaklar Listesi

Fazlar mantıksal sıradadır. **Faz 1'den itibaren her zaman çalışan, demo yapılabilir bir sistem vardır**; sonraki fazlar onun parçalarını derinleştirir. Görevlerin ayrıntıları ve kabul kriterleri [GitHub Issues](https://github.com/mhmtemnbgr1/Aegis/issues) altında.

## Kesme Çizgileri

Geride kalınırsa önceden kararlaştırılmış sırayla kesilir:

1. Test ajanı çıkarılır. Patch'ler en fazla `plausible` düzeyinde yayınlanır.
2. Patch üretimi (Faz 5) tamamen çıkarılır. K3 "gelecek çalışma" olur; K1 ve K2 savunulur.
3. Hafızada yalnızca yapısal + vektör arama kalır; BM25 ve RRF çıkarılır.

Faz 1–4 ve Faz 6 kesilmez.

---

## Faz 0 — Altyapı

- [x] Depo yapısı, `pyproject.toml`, `uv` ortamı
- [x] GitHub Actions CI, issue/PR şablonları
- [x] `aegis --version` komutu
- [x] Hedef repoların seçimi ([docs/target-repos.md](docs/target-repos.md))
- [ ] mypy ve pre-commit
- [ ] Geliştirme ortamı: Ollama ve Gemini API anahtarı
- [ ] GitHub Projects panosu ve branch koruması
- [ ] Görev dağılımı
- [ ] Proje yönünün danışmana onaylatılması

## Faz 1 — Uçtan Uca İskelet

Amaç: En basit haliyle bütün hattı çalıştırmak: PR → risk → LLM → PR yorumu.

- [ ] Diff ayrıştırma ve ön filtre (binary, lock, üretilmiş dosyalar)
- [ ] Sezgisel gatekeeper (değişen satır + riskli yol/API); deneylerde taban çizgisi olarak da kullanılır
- [ ] `LLMProvider` protokolü ve 4 sağlayıcı adaptörü
- [ ] Structured output, retry ve yanıt cache'i
- [ ] Analiz ajanı prompt'ları (versiyonlu)
- [ ] Kanıt ve satır doğrulama filtreleri
- [ ] Prompt injection önlemleri ve saldırı testleri
- [ ] `aegis review --base main`
- [ ] `action.yml` (composite action)
- [ ] Özet yorumu (oluştur / güncelle)
- [ ] Bulguların satır yorumu olarak yayınlanması
- [ ] Fail-open ve check run sonucu
- [ ] Kendi repomuzda dogfooding

## Faz 2 — Repo Madenciliği

- [ ] Miner: PyDriller ile commit, dosya ve fonksiyon değişiklikleri
- [ ] Fix-commit tespiti
- [ ] Fix-commit tespiti için 200 örneklik doğrulama seti
- [ ] SZZ
- [ ] Kamei JIT metrikleri
- [ ] Artımlı madencilik
- [ ] Sentetik git deposu testleri
- [ ] D1 veri setinin çıkarılması (6 repo, önce tqdm pilotu)

## Faz 3 — ML Gatekeeper

- [ ] Zaman sıralı bölme ve etiket gecikmesi tamponu
- [ ] LR, Random Forest ve LightGBM
- [ ] Sınıf dengesizliği yöntemleri
- [ ] Repo içi ve repolar arası değerlendirme
- [ ] Kalibrasyon, bütçe tabanlı eşik, risk bantları
- [ ] SHAP açıklamaları
- [ ] `aegis train` ve `aegis score`
- [ ] Sezgisel gatekeeper'ın eğitilmiş modelle değiştirilmesi
- [ ] Bütçe–recall eğrisi (ilk sonuçlar)

## Faz 4 — Bug-Fix Hafızası

- [ ] Hata kartı modeli ve oluşturucu
- [ ] Fonksiyon düzeyinde parçalama
- [ ] Embedding ve LanceDB indeksi
- [ ] Hibrit arama (yapısal + BM25 + vektör, RRF)
- [ ] Zamansal filtre
- [ ] Getirme değerlendirmesi (Recall@k, MRR)
- [ ] `aegis index` ve artımlı güncelleme
- [ ] Hata kartlarının analiz prompt'una eklenmesi (`memory_refs`)
- [ ] Hafıza sinyalinin gatekeeper'a özellik olarak eklenmesi
- [ ] Model ve indeksin `actions/cache` ile taşınması
- [ ] `main` merge'lerinde hafıza ve model güncelleme workflow'u

## Faz 5 — Patch Üretimi ve Doğrulama

- [ ] Düzeltme ajanı
- [ ] Test ajanı
- [ ] Docker sandbox (RQ3 repoları: tqdm, black, httpie)
- [ ] Doğrulayıcı
- [ ] Geri besleme döngüsü
- [ ] Orkestratör durum makinesi
- [ ] Suggestion blokları ve statüye göre yayın

## Faz 6 — Değerlendirme

- [ ] D1–D4 veri setlerinin tamamlanması (D2'de ~100 elle etiketli örnek)
- [ ] RQ1: ucuz LLM triage taban çizgisi
- [ ] RQ2: hafızasız / plasebo / vektör / hibrit karşılaştırması
- [ ] RQ3: tek çağrı ile çok ajanlı zincirin karşılaştırması
- [ ] RQ4: PR-Agent karşılaştırması
- [ ] `aegis eval` ile tüm deneyler
- [ ] İstatistiksel testler, tablolar, grafikler
- [ ] Patch'lerin elle doğruluk incelemesi
- [ ] LLM eğitim verisi kirliliği alt kümesi
- [ ] Dogfooding verileri

## Faz 7 — Sunum ve Tez

Gereklilikler: [docs/presentation.md](docs/presentation.md)

- [ ] Tez metni
- [ ] Kaynakçanın doğrulanması
- [ ] Demo reposu ve demo PR'ları
- [ ] Canlı demo provası ve yedek video
- [ ] Jüri sorularının sonuç rakamlarıyla güncellenmesi
- [ ] Veri setinin açık lisansla yayınlanması
- [ ] Bildiri (UYMS veya benzeri)
