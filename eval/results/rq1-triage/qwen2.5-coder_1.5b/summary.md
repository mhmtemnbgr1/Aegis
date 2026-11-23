# RQ1 — ucuz LLM triage: qwen2.5-coder:1.5b

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
