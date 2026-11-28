# RQ2 sonuçları (revert seti) — qwen2.5-coder:7b

`eval/rq2.py ozet` ile üretilir. Satır eşleşme toleransı ±3. Yalnız tüm varyantlarda başarılı sonucu olan örnekler sayılır (eşleştirilmiş tasarım).

## Tüm örnekler

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

## Bilgi kesiminden sonraki commit'ler (#55)

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

## Elle doğrulanmış alt küme (#69)

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

