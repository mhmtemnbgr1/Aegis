# RQ2 sonuçları (szz seti) — qwen2.5-coder:7b

`eval/rq2.py ozet` ile üretilir. Satır eşleşme toleransı ±3. Yalnız tüm varyantlarda başarılı sonucu olan örnekler sayılır (eşleştirilmiş tasarım).

## Tüm örnekler

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

## Bilgi kesiminden sonraki commit'ler (#55)

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

## Elle doğrulanmış alt küme (#69)

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

