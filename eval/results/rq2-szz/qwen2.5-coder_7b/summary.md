# RQ2 sonuçları (szz seti) — qwen2.5-coder:7b

`eval/rq2.py ozet` ile üretilir. Satır eşleşme toleransı ±3. Yalnız tüm varyantlarda başarılı sonucu olan örnekler sayılır (eşleştirilmiş tasarım).

## Tüm örnekler

| Varyant | Örnek | Precision | Recall (satır) | F1 | Tespit (hatalı) | Yanlış alarm (temiz) | Hata | Ort. süre | Ort. girdi token |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| none | 600 | %38,9 | %8,0 | %13,2 | 57/300 | 127/300 | 0 | 18.4 sn | 2536 |
| placebo | 600 | %45,8 | %6,4 | %11,2 | 51/300 | 91/300 | 0 | 38.9 sn | 3349 |
| vector | 600 | %52,7 | %7,6 | %13,3 | 52/300 | 82/300 | 0 | 42.2 sn | 3294 |
| hybrid | 600 | %47,8 | %4,4 | %8,0 | 30/300 | 75/300 | 0 | 47.2 sn | 3336 |

**McNemar — Tespit (hatalı commit):**

| Karşılaştırma | Yalnız ilki | Yalnız ikincisi | p | p (Holm) |
| --- | --- | --- | --- | --- |
| hybrid − none | 18 | 45 | 0.001 | 0.004 |
| hybrid − placebo | 8 | 29 | 0.001 | 0.004 |
| vector − none | 30 | 35 | 0.620 | 1.000 |
| vector − placebo | 24 | 23 | 1.000 | 1.000 |
| placebo − none | 23 | 29 | 0.488 | 1.000 |
| hybrid − vector | 8 | 30 | 0.000 | 0.003 |

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
| none | 17 | %37,5 | %5,9 | %10,2 | 3/12 | 2/5 | 0 | 17.0 sn | 2389 |
| placebo | 17 | %33,3 | %9,8 | %15,2 | 1/12 | 1/5 | 0 | 34.3 sn | 3271 |
| vector | 17 | %100,0 | %7,8 | %14,5 | 1/12 | 1/5 | 0 | 40.1 sn | 3372 |
| hybrid | 17 | %100,0 | %9,8 | %17,9 | 1/12 | 1/5 | 0 | 50.4 sn | 3122 |

**McNemar — Tespit (hatalı commit):**

| Karşılaştırma | Yalnız ilki | Yalnız ikincisi | p | p (Holm) |
| --- | --- | --- | --- | --- |
| hybrid − none | 1 | 3 | 0.625 | 1.000 |
| hybrid − placebo | 0 | 0 | 1.000 | 1.000 |
| vector − none | 1 | 3 | 0.625 | 1.000 |
| vector − placebo | 1 | 1 | 1.000 | 1.000 |
| placebo − none | 1 | 3 | 0.625 | 1.000 |
| hybrid − vector | 1 | 1 | 1.000 | 1.000 |

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
| none | 43 | %40,0 | %6,9 | %11,8 | 2/10 | 13/33 | 0 | 20.5 sn | 2441 |
| placebo | 43 | %50,0 | %1,7 | %3,3 | 1/10 | 11/33 | 0 | 38.9 sn | 3450 |
| vector | 43 | %0,0 | %0,0 | %0,0 | 0/10 | 10/33 | 0 | 40.4 sn | 3199 |
| hybrid | 43 | %0,0 | %0,0 | %0,0 | 0/10 | 8/33 | 0 | 45.6 sn | 3105 |

**McNemar — Tespit (hatalı commit):**

| Karşılaştırma | Yalnız ilki | Yalnız ikincisi | p | p (Holm) |
| --- | --- | --- | --- | --- |
| hybrid − none | 0 | 2 | 0.500 | 1.000 |
| hybrid − placebo | 0 | 1 | 1.000 | 1.000 |
| vector − none | 0 | 2 | 0.500 | 1.000 |
| vector − placebo | 0 | 1 | 1.000 | 1.000 |
| placebo − none | 1 | 2 | 1.000 | 1.000 |
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

