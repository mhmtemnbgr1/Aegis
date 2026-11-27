# RQ2 sonuçları (revert seti) — qwen2.5-coder:7b

`eval/rq2.py ozet` ile üretilir. Satır eşleşme toleransı ±3. Yalnız tüm varyantlarda başarılı sonucu olan örnekler sayılır (eşleştirilmiş tasarım).

## Tüm örnekler

| Varyant | Örnek | Precision | Recall (satır) | F1 | Tespit (hatalı) | Yanlış alarm (temiz) | Hata | Ort. süre | Ort. girdi token |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| none | 600 | %92,8 | %15,6 | %26,7 | 126/300 | 127/300 | 0 | 11.9 sn | 2185 |
| placebo | 600 | %95,9 | %11,1 | %19,9 | 104/300 | 91/300 | 0 | 31.4 sn | 3278 |
| vector | 600 | %93,5 | %9,4 | %17,0 | 81/300 | 82/300 | 0 | 31.1 sn | 3164 |
| hybrid | 600 | %95,0 | %7,6 | %14,0 | 73/300 | 75/300 | 0 | 37.5 sn | 3190 |

**McNemar — Tespit (hatalı commit):**

| Karşılaştırma | Yalnız ilki | Yalnız ikincisi | p | p (Holm) |
| --- | --- | --- | --- | --- |
| hybrid − none | 19 | 72 | 0.000 | 0.000 |
| hybrid − placebo | 21 | 52 | 0.000 | 0.001 |
| vector − none | 25 | 70 | 0.000 | 0.000 |
| vector − placebo | 23 | 46 | 0.008 | 0.023 |
| placebo − none | 29 | 51 | 0.018 | 0.037 |
| hybrid − vector | 24 | 32 | 0.350 | 0.350 |

**McNemar — Yanlış alarm (temiz):**

| Karşılaştırma | Yalnız ilki | Yalnız ikincisi | p | p (Holm) |
| --- | --- | --- | --- | --- |
| hybrid − none | 31 | 83 | 0.000 | 0.000 |
| hybrid − placebo | 31 | 47 | 0.089 | 0.266 |
| vector − none | 36 | 81 | 0.000 | 0.000 |
| vector − placebo | 35 | 44 | 0.368 | 0.736 |
| placebo − none | 29 | 65 | 0.000 | 0.001 |
| hybrid − vector | 25 | 32 | 0.427 | 0.736 |

## Bilgi kesiminden sonraki commit'ler (#55)

| Varyant | Örnek | Precision | Recall (satır) | F1 | Tespit (hatalı) | Yanlış alarm (temiz) | Hata | Ort. süre | Ort. girdi token |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| none | 40 | %84,6 | %6,0 | %11,2 | 11/35 | 2/5 | 0 | 10.2 sn | 2047 |
| placebo | 40 | %100,0 | %3,0 | %5,8 | 6/35 | 1/5 | 0 | 26.0 sn | 3195 |
| vector | 40 | %100,0 | %3,4 | %6,5 | 6/35 | 1/5 | 0 | 32.8 sn | 3093 |
| hybrid | 40 | %100,0 | %3,0 | %5,8 | 6/35 | 1/5 | 0 | 45.1 sn | 3012 |

**McNemar — Tespit (hatalı commit):**

| Karşılaştırma | Yalnız ilki | Yalnız ikincisi | p | p (Holm) |
| --- | --- | --- | --- | --- |
| hybrid − none | 2 | 7 | 0.180 | 1.000 |
| hybrid − placebo | 3 | 3 | 1.000 | 1.000 |
| vector − none | 2 | 7 | 0.180 | 1.000 |
| vector − placebo | 3 | 3 | 1.000 | 1.000 |
| placebo − none | 2 | 7 | 0.180 | 1.000 |
| hybrid − vector | 3 | 3 | 1.000 | 1.000 |

**McNemar — Yanlış alarm (temiz):**

| Karşılaştırma | Yalnız ilki | Yalnız ikincisi | p | p (Holm) |
| --- | --- | --- | --- | --- |
| hybrid − none | 0 | 1 | 1.000 | 1.000 |
| hybrid − placebo | 0 | 0 | 1.000 | 1.000 |
| vector − none | 0 | 1 | 1.000 | 1.000 |
| vector − placebo | 0 | 0 | 1.000 | 1.000 |
| placebo − none | 0 | 1 | 1.000 | 1.000 |
| hybrid − vector | 0 | 0 | 1.000 | 1.000 |

## Elle doğrulanmış alt küme (#69)

| Varyant | Örnek | Precision | Recall (satır) | F1 | Tespit (hatalı) | Yanlış alarm (temiz) | Hata | Ort. süre | Ort. girdi token |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| none | 33 | %0,0 | %0,0 | %0,0 | 0/0 | 13/33 | 0 | 19.2 sn | 2306 |
| placebo | 33 | %0,0 | %0,0 | %0,0 | 0/0 | 11/33 | 0 | 33.9 sn | 3351 |
| vector | 33 | %0,0 | %0,0 | %0,0 | 0/0 | 10/33 | 0 | 34.2 sn | 3190 |
| hybrid | 33 | %0,0 | %0,0 | %0,0 | 0/0 | 8/33 | 0 | 41.4 sn | 3057 |

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
| hybrid − none | 5 | 10 | 0.302 | 1.000 |
| hybrid − placebo | 2 | 5 | 0.453 | 1.000 |
| vector − none | 5 | 8 | 0.581 | 1.000 |
| vector − placebo | 3 | 4 | 1.000 | 1.000 |
| placebo − none | 6 | 8 | 0.791 | 1.000 |
| hybrid − vector | 1 | 3 | 0.625 | 1.000 |

