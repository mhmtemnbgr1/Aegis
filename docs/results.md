# Sonuçlar

> Bu belge `eval/results.py` ile üretilir; elle düzenlemeyin. Bölüm 1–6 LLM'siz, bölüm 7–8 yerel Ollama modeliyle koşulan deneylerdir (`docs/llm-experiments.md`); RQ4 burada yok. Yöntem ayrıntıları ve sınırlamalar `docs/architecture.md` ve `docs/mining-schema.md` içinde.

## 1. Veri

| Repo | Commit | Fix | Hatalı commit | Oran | PR | Hatalı PR | PR stili |
| --- | --- | --- | --- | --- | --- | --- | --- |
| scrapy | 9.625 | 1.140 | 1.139 | %11,8 | 2.961 | 450 | merge |
| luigi | 3.047 | 543 | 595 | %19,5 | 1.824 | 407 | merge |
| tornado | 4.138 | 658 | 578 | %14,0 | 1.041 | 161 | merge |
| sanic | 2.112 | 390 | 505 | %23,9 | 1.218 | 366 | merge |
| tqdm | 1.821 | 400 | 396 | %21,8 | 61 | 21 | merge |
| black | 2.502 | 541 | 386 | %15,4 | 2.012 | 273 | squash |

Toplam 23.245 commit. 9.117 PR. Pencere: tüm geçmiş (#13).

200 hatalı commit eşiğinin altında kaldığı için D1'e alınmayan repolar: fastapi (138), httpie (168). Seçim ve gerekçe: `docs/target-repos.md`.

## 2. Etiket kalitesi (#8, #9)

Son etiketler iki bağımsız öneri seti görülerek bir ekip üyesince verildi (yöntem ve sınırlamalar: `docs/mining-schema.md`, Etiket kalitesi).

| Set | Karar – öneri 1 κ | Karar – öneri 2 κ | Öneri 1 – öneri 2 κ |
| --- | --- | --- | --- |
| SZZ eşlemeleri (50) | 0,87 | 0,76 | 0,67 |
| Fix commit'leri (200) | 0,89 | 0,96 | 0,90 |

- **SZZ eşleme doğruluğu:** 15/48 = %31,2 [18,8; 43,8] (%95 GA).
- **Fix sınıflandırıcısı** (`eval/tune_fix.py`; aynı 200 commit'te ayarlandı, iyimser):

| Varyant | Precision | Recall (ağırlıklı) | Popülasyonda fix |
| --- | --- | --- | --- |
| mevcut | 67/95 = %71 | %79 | 3738 |
| +dışlama | 66/77 = %86 | %78 | 3126 |
| +dışlama +başlık | 52/54 = %96 | %63 | 2317 |

## 3. RQ1 — Risk modeli (commit düzeyi, tek zaman bölmesi)

Varsayılan özellik seti (Kamei + riskli yol + test oranı + hafıza), sigmoid kalibrasyon, zaman sıralı bölme. Repolar arası: model yalnızca diğer 5 repoyla eğitilir, aynı test kümesi.

| Model | Senaryo | ROC-AUC | PR-AUC | Recall@%20 efor | Brier | ECE |
| --- | --- | --- | --- | --- | --- | --- |
| lr | repo içi | 0,797 | 0,288 | 0,636 | 0,086 | 0,044 |
| rf | repo içi | 0,770 | 0,253 | 0,626 | 0,089 | 0,048 |
| lightgbm | repo içi | 0,761 | 0,255 | 0,642 | 0,089 | 0,052 |
| lr | repolar arası | 0,805 | 0,300 | 0,657 | 0,084 | 0,042 |
| rf | repolar arası | 0,802 | 0,289 | 0,680 | 0,083 | 0,038 |
| lightgbm | repolar arası | 0,793 | 0,310 | 0,656 | 0,083 | 0,033 |

Ortalama 6 repo üzerinden. Repolar arası genel model repo içi modelden geri kalmıyor; hafıza sayımları (geçmiş hata kartı) repolar arasında iyi genelleşiyor.

## 4. RQ1 — Maliyet–recall eğrisi (PR düzeyi, kayan pencere)

25 birim (5 repo × 5 zaman penceresi; tqdm 61 PR ile dışarıda). Her pencerede modeller yalnızca pencereden önceki commit'lerle eğitildi; RF 5 tohum ortalaması. Hücre: yakalanan hatalı PR oranı, ortalama [%95 bootstrap GA].

![Maliyet–recall eğrisi](figures/rq1-curve.svg)

| Yöntem | %10 LLM | %20 LLM | %40 LLM | %60 LLM |
| --- | --- | --- | --- | --- |
| LR (tam + hafıza) | %37,6 [32,7; 43,1] | %59,1 [53,4; 64,7] | %82,0 [76,9; 86,8] | %94,1 [91,2; 96,6] |
| RF (tam + hafıza) | %35,2 [30,5; 39,8] | %54,6 [49,3; 60,2] | %80,2 [75,3; 84,8] | %92,6 [89,2; 95,6] |
| LR (tam) | %33,2 [27,5; 39,3] | %54,4 [48,0; 60,4] | %79,5 [74,2; 84,7] | %91,5 [87,7; 94,8] |
| RF (tam) | %30,2 [26,1; 34,1] | %49,9 [45,2; 54,5] | %77,7 [72,7; 82,6] | %91,3 [88,3; 94,1] |
| LR (Kamei) | %33,1 [28,3; 37,9] | %52,1 [46,5; 57,6] | %78,0 [72,7; 83,1] | %90,0 [86,1; 93,4] |
| LR (hafıza plasebosu) | %33,5 [27,5; 39,7] | %54,7 [48,1; 60,8] | %79,6 [74,2; 84,7] | %91,3 [87,7; 94,5] |
| RF (hafıza plasebosu) | %33,5 [28,6; 38,7] | %49,9 [43,6; 56,6] | %76,2 [71,0; 81,5] | %92,1 [89,2; 94,7] |
| Sezgisel kural | %29,3 [24,8; 34,0] | %49,3 [43,7; 55,2] | %74,7 [70,1; 79,6] | %89,1 [85,3; 92,6] |
| Rastgele | %10 | %20 | %40 | %60 |

**İşletme noktaları** (eşik önceki pencereden, ölçüm mevcut pencerede):

| Nokta | Yöntem | Eleme (LLM'e gitmeyen) | Recall |
| --- | --- | --- | --- |
| maliyet odaklı (hedef %60 eleme) | LR (tam + hafıza) | %58,3 [52,9; 63,1] | %82,2 [75,6; 87,9] |
| maliyet odaklı (hedef %60 eleme) | Sezgisel kural | %57,7 [53,8; 61,7] | %75,0 [69,4; 80,7] |
| güvenlik odaklı (hedef ≥ %90 recall) | LR (tam + hafıza) | %53,9 [46,2; 61,9] | %82,7 [74,7; 89,6] |
| güvenlik odaklı (hedef ≥ %90 recall) | Sezgisel kural | %41,1 [33,0; 48,9] | %86,0 [79,3; 91,6] |

**Eşleştirilmiş karşılaştırmalar, %10 LLM payında:**

| Karşılaştırma | Ortalama fark (puan) | Wilcoxon p (Holm) | Etki (r) |
| --- | --- | --- | --- |
| LR (tam + hafıza) − sezgisel | +8,3 | 0,028 | 0,66 |
| RF (tam + hafıza) − sezgisel | +5,9 | 0,050 | 0,61 |
| LR: hafıza − tam | +4,4 | 0,007 | 0,82 |
| RF: hafıza − tam | +5,0 | 0,045 | 0,70 |
| LR: hafıza − plasebo | +4,1 | 0,012 | 0,86 |
| RF: hafıza − plasebo | +1,7 | 0,510 | 0,32 |
| LR: plasebo − tam | +0,3 | 0,510 | 0,28 |

**Eşleştirilmiş karşılaştırmalar, %20 LLM payında:**

| Karşılaştırma | Ortalama fark (puan) | Wilcoxon p (Holm) | Etki (r) |
| --- | --- | --- | --- |
| LR (tam + hafıza) − sezgisel | +9,8 | < 0,001 | 0,94 |
| RF (tam + hafıza) − sezgisel | +5,3 | 0,090 | 0,53 |
| LR: hafıza − tam | +4,7 | 0,070 | 0,66 |
| RF: hafıza − tam | +4,7 | 0,034 | 0,74 |
| LR: hafıza − plasebo | +4,4 | 0,090 | 0,62 |
| RF: hafıza − plasebo | +4,6 | 0,070 | 0,64 |
| LR: plasebo − tam | +0,2 | 0,600 | 0,24 |

**Eşleştirilmiş karşılaştırmalar, %40 LLM payında:**

| Karşılaştırma | Ortalama fark (puan) | Wilcoxon p (Holm) | Etki (r) |
| --- | --- | --- | --- |
| LR (tam + hafıza) − sezgisel | +7,3 | 0,016 | 0,81 |
| RF (tam + hafıza) − sezgisel | +5,5 | 0,031 | 0,72 |
| LR: hafıza − tam | +2,5 | 0,223 | 0,47 |
| RF: hafıza − tam | +2,5 | 0,112 | 0,67 |
| LR: hafıza − plasebo | +2,4 | 0,207 | 0,53 |
| RF: hafıza − plasebo | +3,9 | 0,007 | 0,91 |
| LR: plasebo − tam | +0,1 | 0,866 | 0,07 |

## 5. RQ2 (LLM'siz) — Hafıza getirme

890 sorgu (6 repo; sorgu = SZZ'ye göre hata getiren commit, ilgili = bu hatayı sonradan düzelten fix'in fonksiyonlarını daha önce düzeltmiş kartlar; yalnızca sorgu tarihinden önceki kartlar aranır). Hücre: ortalama [%95 bootstrap GA].

| Mod | Recall@1 | Recall@5 | MRR |
| --- | --- | --- | --- |
| Hibrit (RRF) | %47,1 [43,7; 50,3] | %63,8 [60,7; 67,0] | 0,540 [0,510; 0,570] |
| Vektör (LSA) | %43,3 [40,1; 46,5] | %61,7 [58,4; 64,8] | 0,507 [0,477; 0,536] |
| BM25 | %41,3 [38,1; 44,6] | %61,2 [58,1; 64,4] | 0,494 [0,466; 0,524] |
| Yapısal | %42,7 [39,4; 46,1] | %58,0 [54,6; 61,1] | 0,490 [0,460; 0,520] |
| Rastgele | %3,1 [2,0; 4,3] | %13,9 [11,7; 16,2] | 0,080 [0,067; 0,094] |

**Hibrit ile diğer modlar (sorgu başına ters sıra):**

| Karşılaştırma | Ortalama fark (MRR) | Wilcoxon p (Holm) | Etki (r) |
| --- | --- | --- | --- |
| hibrit − vektör (lsa) | +0,034 | < 0,001 | 0,40 |
| hibrit − bm25 | +0,046 | < 0,001 | 0,42 |
| hibrit − yapısal | +0,051 | < 0,001 | 0,47 |
| hibrit − rastgele | +0,460 | < 0,001 | 0,94 |

## 6. Gerçek PR'larda çalıştırma (D4)

54 Action çalıştırması, 28 PR (mhmtemnbgr1/Aegis: 50, mhmtemnbgr1/cli: 4). Kaynak: Action'ın yüklediği `runs.jsonl` kayıtları (`eval/d4.py`, artifact'lar 90 gün saklanır). GitHub runner'larında Ollama olmadığı için LLM incelemesi bu çalıştırmalarda yoktur; süreler gatekeeper, hafıza ve deterministik denetimleri kapsar.

| Ölçü | Değer |
| --- | --- |
| LLM kapalı (runner'da Ollama yok) | 39 |
| düşük risk, LLM'e gönderilmedi | 11 |
| LLM'e ulaşılamadı (fail-open) | 4 |
| Risk bandı (düşük / orta / yüksek) | 11 / 39 / 4 |
| Süre: medyan / p95 / en uzun | 0,02 / 4,28 / 4,63 sn |
| Bulgu üreten çalıştırma (deterministik denetimler) | 12 |
| Özet yorumuna tepki (👍 / 👎) | 0 / 0 |

Hiçbir çalıştırma PR'ı engellemedi; LLM'e ulaşılamayan 4 çalıştırma da uyarıyla tamamlandı.

## 7. RQ1 — Ucuz LLM triage (qwen2.5-coder:1.5b)

Bölüm 4'teki 25 pencerenin her birinden 50 PR örneklendi ve küçük bir yerel modele "bu PR hatalı mı" diye puanlatıldı; aynı PR'lar aynı paylarla risk modeli ve sezgisel kuralla karşılaştırılır.

`eval/rq1_triage.py ozet` ile üretilir. 1250 PR yanıtlandı (0 hata), 25 pencere. Hücre: yakalanan hatalı PR oranı, pencereler üzerinden ortalama [%95 bootstrap GA]; yöntemler aynı PR'ları puanlar.

| Yöntem | %10 LLM | %20 LLM | %40 LLM | %60 LLM |
| --- | --- | --- | --- | --- |
| LLM triage (qwen2.5-coder:1.5b) | %9,2 [5,3; 13,5] | %23,0 [15,7; 30,4] | %53,3 [44,0; 62,1] | %84,0 [76,6; 90,9] |
| LR (tam + hafıza) | %37,5 [28,8; 47,5] | %63,0 [55,4; 71,1] | %84,9 [78,8; 90,6] | %94,4 [90,7; 97,7] |
| Sezgisel | %24,8 [17,4; 34,2] | %49,1 [40,6; 58,3] | %74,1 [65,4; 81,3] | %92,4 [88,3; 96,2] |

**Eşleştirilmiş karşılaştırma (Wilcoxon, pencereler):**

| Pay | LR − LLM (puan) | p | LLM − sezgisel (puan) | p |
| --- | --- | --- | --- | --- |
| %10 | +28,3 | 0,000 | -15,6 | 0,001 |
| %20 | +40,0 | 0,000 | -26,1 | 0,000 |
| %40 | +31,5 | 0,000 | -20,8 | 0,000 |
| %60 | +10,3 | 0,018 | -8,4 | 0,003 |

**Triage maliyeti:** PR başına ortalama 0.8 sn, 1308 girdi + 61 çıktı token. Risk modeli puanlama maliyeti ihmal edilebilir (CPU, milisaniyeler).

## 8. RQ2 — Hafızalı LLM incelemesi (qwen2.5-coder:7b)

Her örnek dört varyantla incelendi: hafızasız (`none`), alakasız kartlar (`placebo`), vektör getirmesi (`vector`) ve hibrit getirme (`hybrid`). Bağlam penceresi 16.384 token (sığmayan istemlerde 32.768), sıcaklık 0. Tespit: hatalı commit'te en az bir bulgunun beklenen hatalı satıra ±3 satır yakın olması; yanlış alarm: temiz commit'te herhangi bir bulgu olması.

### 8.1. Revert seti

`eval/rq2.py ozet` ile üretilir. Satır eşleşme toleransı ±3. Yalnız tüm varyantlarda başarılı sonucu olan örnekler sayılır (eşleştirilmiş tasarım).

#### Tüm örnekler

| Varyant | Örnek | Precision | Recall (satır) | F1 | Tespit (hatalı) | Yanlış alarm (temiz) | Hata | Ort. süre | Ort. girdi token |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| none | 582 | %93,8 | %17,2 | %29,1 | 130/288 | 144/294 | 4 | 11.4 sn | 2303 |
| placebo | 582 | %96,1 | %15,4 | %26,6 | 117/288 | 127/294 | 7 | 14.7 sn | 3860 |
| vector | 582 | %95,2 | %13,1 | %23,0 | 106/288 | 130/294 | 5 | 15.1 sn | 4220 |
| hybrid | 582 | %97,5 | %12,9 | %22,8 | 107/288 | 122/294 | 7 | 15.0 sn | 4362 |

**McNemar — Tespit (hatalı commit):**

| Karşılaştırma | Yalnız ilki | Yalnız ikincisi | p | p (Holm) |
| --- | --- | --- | --- | --- |
| hybrid − none | 29 | 52 | 0.014 | 0.070 |
| hybrid − placebo | 31 | 41 | 0.289 | 0.725 |
| vector − none | 28 | 52 | 0.010 | 0.058 |
| vector − placebo | 31 | 42 | 0.242 | 0.725 |
| placebo − none | 29 | 42 | 0.154 | 0.616 |
| hybrid − vector | 21 | 20 | 1.000 | 1.000 |

**McNemar — Yanlış alarm (temiz):**

| Karşılaştırma | Yalnız ilki | Yalnız ikincisi | p | p (Holm) |
| --- | --- | --- | --- | --- |
| hybrid − none | 43 | 65 | 0.043 | 0.257 |
| hybrid − placebo | 37 | 42 | 0.653 | 1.000 |
| vector − none | 45 | 59 | 0.202 | 0.809 |
| vector − placebo | 41 | 38 | 0.822 | 1.000 |
| placebo − none | 44 | 61 | 0.118 | 0.590 |
| hybrid − vector | 23 | 31 | 0.341 | 1.000 |

#### Bilgi kesiminden sonraki commit'ler (#55)

| Varyant | Örnek | Precision | Recall (satır) | F1 | Tespit (hatalı) | Yanlış alarm (temiz) | Hata | Ort. süre | Ort. girdi token |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| none | 39 | %90,9 | %7,2 | %13,3 | 10/34 | 2/5 | 0 | 13.7 sn | 2353 |
| placebo | 39 | %91,3 | %10,4 | %18,6 | 9/34 | 2/5 | 1 | 24.1 sn | 4202 |
| vector | 39 | %100,0 | %5,2 | %9,8 | 9/34 | 1/5 | 0 | 16.9 sn | 4684 |
| hybrid | 39 | %91,7 | %8,0 | %14,7 | 11/34 | 2/5 | 0 | 15.2 sn | 4766 |

**McNemar — Tespit (hatalı commit):**

| Karşılaştırma | Yalnız ilki | Yalnız ikincisi | p | p (Holm) |
| --- | --- | --- | --- | --- |
| hybrid − none | 3 | 2 | 1.000 | 1.000 |
| hybrid − placebo | 4 | 2 | 0.688 | 1.000 |
| vector − none | 1 | 2 | 1.000 | 1.000 |
| vector − placebo | 3 | 3 | 1.000 | 1.000 |
| placebo − none | 3 | 4 | 1.000 | 1.000 |
| hybrid − vector | 3 | 1 | 0.625 | 1.000 |

**McNemar — Yanlış alarm (temiz):**

| Karşılaştırma | Yalnız ilki | Yalnız ikincisi | p | p (Holm) |
| --- | --- | --- | --- | --- |
| hybrid − none | 1 | 1 | 1.000 | 1.000 |
| hybrid − placebo | 0 | 0 | 1.000 | 1.000 |
| vector − none | 0 | 1 | 1.000 | 1.000 |
| vector − placebo | 0 | 1 | 1.000 | 1.000 |
| placebo − none | 1 | 1 | 1.000 | 1.000 |
| hybrid − vector | 1 | 0 | 1.000 | 1.000 |

#### Elle doğrulanmış alt küme (#69)

| Varyant | Örnek | Precision | Recall (satır) | F1 | Tespit (hatalı) | Yanlış alarm (temiz) | Hata | Ort. süre | Ort. girdi token |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| none | 33 | %0,0 | %0,0 | %0,0 | 0/0 | 17/33 | 0 | 11.3 sn | 2502 |
| placebo | 33 | %0,0 | %0,0 | %0,0 | 0/0 | 15/33 | 0 | 12.3 sn | 4072 |
| vector | 33 | %0,0 | %0,0 | %0,0 | 0/0 | 15/33 | 0 | 20.8 sn | 4633 |
| hybrid | 33 | %0,0 | %0,0 | %0,0 | 0/0 | 13/33 | 0 | 12.3 sn | 4722 |

**McNemar — Tespit (hatalı commit):**

| Karşılaştırma | Yalnız ilki | Yalnız ikincisi | p | p (Holm) |
| --- | --- | --- | --- | --- |
| hybrid − none | 0 | 0 | 1.000 | 1.000 |
| hybrid − placebo | 0 | 0 | 1.000 | 1.000 |
| vector − none | 0 | 0 | 1.000 | 1.000 |
| vector − placebo | 0 | 0 | 1.000 | 1.000 |
| placebo − none | 0 | 0 | 1.000 | 1.000 |
| hybrid − vector | 0 | 0 | 1.000 | 1.000 |

**McNemar — Yanlış alarm (temiz):**

| Karşılaştırma | Yalnız ilki | Yalnız ikincisi | p | p (Holm) |
| --- | --- | --- | --- | --- |
| hybrid − none | 4 | 8 | 0.388 | 1.000 |
| hybrid − placebo | 2 | 4 | 0.688 | 1.000 |
| vector − none | 5 | 7 | 0.774 | 1.000 |
| vector − placebo | 3 | 3 | 1.000 | 1.000 |
| placebo − none | 6 | 8 | 0.791 | 1.000 |
| hybrid − vector | 0 | 2 | 0.500 | 1.000 |


### 8.2. SZZ seti (gerçekçilik; temiz örnekler revert setiyle ortak)

`eval/rq2.py ozet` ile üretilir. Satır eşleşme toleransı ±3. Yalnız tüm varyantlarda başarılı sonucu olan örnekler sayılır (eşleştirilmiş tasarım).

#### Tüm örnekler

| Varyant | Örnek | Precision | Recall (satır) | F1 | Tespit (hatalı) | Yanlış alarm (temiz) | Hata | Ort. süre | Ort. girdi token |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| none | 588 | %36,5 | %8,5 | %13,8 | 63/294 | 144/294 | 3 | 14.9 sn | 2820 |
| placebo | 588 | %42,5 | %9,9 | %16,0 | 76/294 | 127/294 | 3 | 16.2 sn | 4335 |
| vector | 588 | %45,2 | %10,9 | %17,6 | 75/294 | 130/294 | 4 | 17.4 sn | 4830 |
| hybrid | 588 | %42,9 | %8,6 | %14,4 | 62/294 | 122/294 | 4 | 17.4 sn | 4962 |

**McNemar — Tespit (hatalı commit):**

| Karşılaştırma | Yalnız ilki | Yalnız ikincisi | p | p (Holm) |
| --- | --- | --- | --- | --- |
| hybrid − none | 30 | 31 | 1.000 | 1.000 |
| hybrid − placebo | 25 | 39 | 0.103 | 0.621 |
| vector − none | 38 | 26 | 0.169 | 0.621 |
| vector − placebo | 30 | 31 | 1.000 | 1.000 |
| placebo − none | 36 | 23 | 0.117 | 0.621 |
| hybrid − vector | 21 | 34 | 0.105 | 0.621 |

**McNemar — Yanlış alarm (temiz):**

| Karşılaştırma | Yalnız ilki | Yalnız ikincisi | p | p (Holm) |
| --- | --- | --- | --- | --- |
| hybrid − none | 43 | 65 | 0.043 | 0.257 |
| hybrid − placebo | 37 | 42 | 0.653 | 1.000 |
| vector − none | 45 | 59 | 0.202 | 0.809 |
| vector − placebo | 41 | 38 | 0.822 | 1.000 |
| placebo − none | 44 | 61 | 0.118 | 0.590 |
| hybrid − vector | 23 | 31 | 0.341 | 1.000 |

#### Bilgi kesiminden sonraki commit'ler (#55)

| Varyant | Örnek | Precision | Recall (satır) | F1 | Tespit (hatalı) | Yanlış alarm (temiz) | Hata | Ort. süre | Ort. girdi token |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| none | 17 | %46,2 | %11,8 | %18,8 | 5/12 | 2/5 | 0 | 16.6 sn | 2447 |
| placebo | 17 | %62,5 | %21,6 | %32,1 | 4/12 | 2/5 | 0 | 25.3 sn | 4380 |
| vector | 17 | %66,7 | %11,8 | %20,0 | 2/12 | 1/5 | 0 | 13.4 sn | 4841 |
| hybrid | 17 | %33,3 | %7,8 | %12,7 | 1/12 | 2/5 | 0 | 13.9 sn | 4992 |

**McNemar — Tespit (hatalı commit):**

| Karşılaştırma | Yalnız ilki | Yalnız ikincisi | p | p (Holm) |
| --- | --- | --- | --- | --- |
| hybrid − none | 1 | 5 | 0.219 | 1.000 |
| hybrid − placebo | 0 | 3 | 0.250 | 1.000 |
| vector − none | 2 | 5 | 0.453 | 1.000 |
| vector − placebo | 1 | 3 | 0.625 | 1.000 |
| placebo − none | 1 | 2 | 1.000 | 1.000 |
| hybrid − vector | 0 | 1 | 1.000 | 1.000 |

**McNemar — Yanlış alarm (temiz):**

| Karşılaştırma | Yalnız ilki | Yalnız ikincisi | p | p (Holm) |
| --- | --- | --- | --- | --- |
| hybrid − none | 1 | 1 | 1.000 | 1.000 |
| hybrid − placebo | 0 | 0 | 1.000 | 1.000 |
| vector − none | 0 | 1 | 1.000 | 1.000 |
| vector − placebo | 0 | 1 | 1.000 | 1.000 |
| placebo − none | 1 | 1 | 1.000 | 1.000 |
| hybrid − vector | 1 | 0 | 1.000 | 1.000 |

#### Elle doğrulanmış alt küme (#69)

| Varyant | Örnek | Precision | Recall (satır) | F1 | Tespit (hatalı) | Yanlış alarm (temiz) | Hata | Ort. süre | Ort. girdi token |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| none | 43 | %33,3 | %8,6 | %13,7 | 3/10 | 17/33 | 0 | 11.5 sn | 2641 |
| placebo | 43 | %42,9 | %5,2 | %9,2 | 3/10 | 15/33 | 0 | 13.4 sn | 4195 |
| vector | 43 | %25,0 | %5,2 | %8,6 | 2/10 | 15/33 | 0 | 19.1 sn | 4763 |
| hybrid | 43 | %16,7 | %3,4 | %5,7 | 1/10 | 13/33 | 0 | 12.1 sn | 4822 |

**McNemar — Tespit (hatalı commit):**

| Karşılaştırma | Yalnız ilki | Yalnız ikincisi | p | p (Holm) |
| --- | --- | --- | --- | --- |
| hybrid − none | 0 | 2 | 0.500 | 1.000 |
| hybrid − placebo | 1 | 3 | 0.625 | 1.000 |
| vector − none | 1 | 2 | 1.000 | 1.000 |
| vector − placebo | 1 | 2 | 1.000 | 1.000 |
| placebo − none | 3 | 3 | 1.000 | 1.000 |
| hybrid − vector | 0 | 1 | 1.000 | 1.000 |

**McNemar — Yanlış alarm (temiz):**

| Karşılaştırma | Yalnız ilki | Yalnız ikincisi | p | p (Holm) |
| --- | --- | --- | --- | --- |
| hybrid − none | 4 | 8 | 0.388 | 1.000 |
| hybrid − placebo | 2 | 4 | 0.688 | 1.000 |
| vector − none | 5 | 7 | 0.774 | 1.000 |
| vector − placebo | 3 | 3 | 1.000 | 1.000 |
| placebo − none | 6 | 8 | 0.791 | 1.000 |
| hybrid − vector | 0 | 2 | 0.500 | 1.000 |


## 9. Geçerlilik notları

- Etiketler SZZ'ye dayanır; elle kontrolde SZZ eşlemelerinin yalnızca ~%31'i doğru çıktı. Tüm RQ1 ve RQ2 sayıları bu gürültülü etiketlere göredir. Issue etiketi, taşınan satır ve tarih süzgeçleri bu veride doğruluğu artırmadı ya da veriyi yok etti (`docs/mining-schema.md`, SZZ süzgeçleri).
- Etiket kalitesi setlerini (#8, #9) tek kişi, iki öneri setini görerek etiketledi; kararların büyük çoğunluğu önerilerle aynı (`docs/mining-schema.md`).
- Hafızanın vektör kolu nöral değil LSA'dır (yerel LLM kurulmadı).
- Fix sınıflandırıcısı aynı 200 commit üzerinde ayarlandı; precision/recall iyimserdir.
- LLM'li deneyler (bölüm 7–8) tek model ve tek koşudur (sıcaklık 0); başka model ya da prompt sonuçları değiştirebilir. Hata veren koşular (RQ2'de %1'in altında) eşleştirilmiş tasarım gereği o örneğin tüm varyantlarıyla birlikte dışarıda kalır.
- RQ2'nin doğrulanmış alt kümesinde (#69) revert setinin hatalı örneği yoktur; alt küme küçüktür (33–43 örnek) ve yalnızca yön gösterir.
