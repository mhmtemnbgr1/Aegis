# Sonuçlar (LLM'siz)

> Bu belge `eval/results.py` ile üretilir; elle düzenlemeyin. LLM gerektiren deneyler (ucuz LLM triage #67, LLM'li RQ2, RQ4) burada yok. Yöntem ayrıntıları ve sınırlamalar `docs/architecture.md` ve `docs/mining-schema.md` içinde.

## 1. Veri

| Repo | Commit | Fix | Hatalı commit | Oran | PR | Hatalı PR | PR stili |
| --- | --- | --- | --- | --- | --- | --- | --- |
| scrapy | 9.625 | 1.140 | 1.139 | %11,8 | 2.961 | 450 | merge |
| tornado | 4.138 | 658 | 578 | %14,0 | 1.041 | 161 | merge |
| tqdm | 1.821 | 400 | 396 | %21,8 | 61 | 21 | merge |
| black | 2.502 | 541 | 386 | %15,4 | 2.012 | 273 | squash |
| httpie | 1.690 | 183 | 168 | %9,9 | 354 | 43 | squash |
| fastapi | 8.037 | 204 | 138 | %1,7 | 3.737 | 105 | squash |

Toplam 27.813 commit. 10.166 PR. Pencere: tüm geçmiş (#13).

## 2. Etiket kalitesi (#8, #9)

Etiketler: Claude Opus 5.5 ve Claude Sonnet 5.5 bağımsız önerileri görülerek bir ekip üyesince verildi (yöntem ve sınırlamalar: `docs/mining-schema.md`, Etiket kalitesi).

| Set | İnsan – Opus κ | İnsan – Sonnet κ | Opus – Sonnet κ |
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
| lr | repo içi | 0,831 | 0,306 | 0,607 | 0,070 | 0,037 |
| rf | repo içi | 0,834 | 0,295 | 0,601 | 0,070 | 0,036 |
| lightgbm | repo içi | 0,816 | 0,278 | 0,550 | 0,070 | 0,039 |
| lr | repolar arası | 0,844 | 0,353 | 0,607 | 0,071 | 0,049 |
| rf | repolar arası | 0,845 | 0,306 | 0,609 | 0,071 | 0,053 |
| lightgbm | repolar arası | 0,819 | 0,294 | 0,552 | 0,071 | 0,046 |

Ortalama 6 repo üzerinden. Repolar arası genel model repo içi modelden geri kalmıyor; hafıza sayımları (geçmiş hata kartı) repolar arasında iyi genelleşiyor.

## 4. RQ1 — Maliyet–recall eğrisi (PR düzeyi, kayan pencere)

25 birim (5 repo × 5 zaman penceresi; tqdm 61 PR ile dışarıda). Her pencerede modeller yalnızca pencereden önceki commit'lerle eğitildi; RF 5 tohum ortalaması. Hücre: yakalanan hatalı PR oranı, ortalama [%95 bootstrap GA].

![Maliyet–recall eğrisi](figures/rq1-curve.svg)

| Yöntem | %10 LLM | %20 LLM | %40 LLM | %60 LLM |
| --- | --- | --- | --- | --- |
| LR (tam + hafıza) | %47,5 [39,6; 55,3] | %64,9 [55,4; 73,8] | %85,5 [79,1; 91,5] | %94,9 [90,0; 98,5] |
| RF (tam + hafıza) | %43,1 [33,4; 53,0] | %61,7 [53,0; 70,3] | %85,7 [79,8; 91,2] | %95,7 [92,6; 98,3] |
| LR (tam) | %43,5 [35,2; 52,0] | %58,0 [48,8; 66,7] | %86,4 [80,5; 91,8] | %92,3 [87,3; 96,3] |
| RF (tam) | %36,2 [28,1; 44,8] | %56,2 [46,6; 65,6] | %84,8 [78,9; 90,6] | %94,5 [91,0; 97,4] |
| LR (Kamei) | %43,0 [35,4; 50,9] | %59,0 [50,3; 67,4] | %86,1 [80,2; 91,5] | %93,0 [88,1; 96,9] |
| LR (hafıza plasebosu) | %43,3 [34,9; 51,9] | %58,0 [49,2; 66,7] | %85,5 [79,5; 90,8] | %92,1 [87,2; 96,0] |
| RF (hafıza plasebosu) | %35,4 [27,5; 43,4] | %57,9 [48,2; 67,4] | %82,6 [76,6; 88,5] | %92,8 [87,8; 96,9] |
| Sezgisel kural | %27,5 [20,7; 34,6] | %52,8 [44,6; 61,1] | %78,2 [72,4; 84,1] | %89,7 [84,2; 94,6] |
| Rastgele | %10 | %20 | %40 | %60 |

**İşletme noktaları** (eşik önceki pencereden, ölçüm mevcut pencerede):

| Nokta | Yöntem | Eleme (LLM'e gitmeyen) | Recall |
| --- | --- | --- | --- |
| maliyet odaklı (hedef %60 eleme) | LR (tam + hafıza) | %58,2 [51,4; 64,7] | %84,0 [73,6; 92,5] |
| maliyet odaklı (hedef %60 eleme) | Sezgisel kural | %59,7 [54,5; 64,9] | %73,3 [63,7; 81,9] |
| güvenlik odaklı (hedef ≥ %90 recall) | LR (tam + hafıza) | %59,4 [46,7; 71,1] | %73,6 [62,9; 83,7] |
| güvenlik odaklı (hedef ≥ %90 recall) | Sezgisel kural | %43,9 [32,9; 54,4] | %80,5 [69,9; 89,2] |

**Eşleştirilmiş karşılaştırmalar, %10 LLM payında:**

| Karşılaştırma | Ortalama fark (puan) | Wilcoxon p (Holm) | Etki (r) |
| --- | --- | --- | --- |
| LR (tam + hafıza) − sezgisel | +19,9 | 0,007 | 0,84 |
| RF (tam + hafıza) − sezgisel | +15,6 | 0,049 | 0,60 |
| LR: hafıza − tam | +4,0 | 0,043 | 0,85 |
| RF: hafıza − tam | +6,9 | 0,049 | 0,68 |
| LR: hafıza − plasebo | +4,2 | 0,043 | 0,93 |
| RF: hafıza − plasebo | +7,7 | 0,043 | 0,74 |
| LR: plasebo − tam | -0,2 | 1,000 | 0,00 |

**Eşleştirilmiş karşılaştırmalar, %20 LLM payında:**

| Karşılaştırma | Ortalama fark (puan) | Wilcoxon p (Holm) | Etki (r) |
| --- | --- | --- | --- |
| LR (tam + hafıza) − sezgisel | +12,1 | 0,032 | 0,76 |
| RF (tam + hafıza) − sezgisel | +9,0 | 0,067 | 0,63 |
| LR: hafıza − tam | +6,8 | 0,057 | 0,74 |
| RF: hafıza − tam | +5,5 | 0,045 | 0,81 |
| LR: hafıza − plasebo | +6,8 | 0,067 | 0,72 |
| RF: hafıza − plasebo | +3,8 | 0,076 | 0,63 |
| LR: plasebo − tam | +0,0 | 0,893 | 0,07 |

**Eşleştirilmiş karşılaştırmalar, %40 LLM payında:**

| Karşılaştırma | Ortalama fark (puan) | Wilcoxon p (Holm) | Etki (r) |
| --- | --- | --- | --- |
| LR (tam + hafıza) − sezgisel | +7,3 | 0,054 | 0,80 |
| RF (tam + hafıza) − sezgisel | +7,5 | 0,033 | 0,89 |
| LR: hafıza − tam | -0,9 | 1,000 | -0,05 |
| RF: hafıza − tam | +0,9 | 0,788 | 0,44 |
| LR: hafıza − plasebo | +0,1 | 1,000 | 0,12 |
| RF: hafıza − plasebo | +3,1 | 0,033 | 1,00 |
| LR: plasebo − tam | -0,9 | 0,788 | -0,60 |

## 5. RQ2 (LLM'siz) — Hafıza getirme

906 sorgu (6 repo; sorgu = SZZ'ye göre hata getiren commit, ilgili = bu hatayı sonradan düzelten fix'in fonksiyonlarını daha önce düzeltmiş kartlar; yalnızca sorgu tarihinden önceki kartlar aranır). Hücre: ortalama [%95 bootstrap GA].

| Mod | Recall@1 | Recall@5 | MRR |
| --- | --- | --- | --- |
| Hibrit (RRF) | %50,6 [47,4; 53,9] | %69,5 [66,6; 72,5] | 0,584 [0,555; 0,613] |
| Vektör (LSA) | %45,9 [42,7; 49,1] | %66,8 [63,7; 69,8] | 0,546 [0,517; 0,574] |
| BM25 | %45,0 [41,8; 48,2] | %66,4 [63,4; 69,5] | 0,539 [0,510; 0,567] |
| Yapısal | %43,2 [40,0; 46,4] | %62,7 [59,6; 65,9] | 0,514 [0,485; 0,543] |
| Rastgele | %4,4 [3,2; 5,8] | %15,2 [13,0; 17,5] | 0,097 [0,082; 0,112] |

**Hibrit ile diğer modlar (sorgu başına ters sıra):**

| Karşılaştırma | Ortalama fark (MRR) | Wilcoxon p (Holm) | Etki (r) |
| --- | --- | --- | --- |
| hibrit − vektör (lsa) | +0,038 | < 0,001 | 0,38 |
| hibrit − bm25 | +0,045 | < 0,001 | 0,41 |
| hibrit − yapısal | +0,070 | < 0,001 | 0,56 |
| hibrit − rastgele | +0,487 | < 0,001 | 0,94 |

## 6. Geçerlilik notları

- Etiketler SZZ'ye dayanır; elle kontrolde SZZ eşlemelerinin yalnızca ~%31'i doğru çıktı. Tüm RQ1 ve RQ2 sayıları bu gürültülü etiketlere göredir.
- Etiket kalitesi setleri LLM önerileri görülerek tek kişi tarafından etiketlendi; fix seti fiilen insan tarafından gözden geçirilmiş LLM etiketidir.
- Hafızanın vektör kolu nöral değil LSA'dır (yerel LLM kurulmadı).
- Fix sınıflandırıcısı aynı 200 commit üzerinde ayarlandı; precision/recall iyimserdir.
