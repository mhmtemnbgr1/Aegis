# Değerlendirme

Ayrıntılar için docs/presentation.md dosyasındaki [Değerlendirme Planı](../docs/presentation.md#5-değerlendirme-planı) bölümüne bakın.

```
eval/
├── datasets/
│   ├── d1-jit/          # SZZ ile etiketlenmiş commit özellikleri (Parquet)
│   ├── d2-detection/    # bug-inducing + temiz commit diff'leri ve beklenen satırlar
│   ├── d3-repair/       # BugsInPy alt kümesi tanımları
│   └── d4-e2e/          # demo ve dogfooding PR kayıtları
├── experiments/         # deney.toml dosyaları (aegis eval <dosya>)
└── reports/             # CSV + grafikler (git'e eklenmez)
```

D2 örnek formatı (`datasets/d2-detection/<id>/`):

```
<id>/
├── diff.patch     # incelenecek değişiklik
└── labels.json    # beklenen bulgular
```

```json
{
  "source": "szz-inducing | clean",
  "repo": "owner/name",
  "commit": "9f8e7d6",
  "commit_date": "2025-11-02T09:15:00Z",
  "fix_commit": "a1b2c3d",
  "language": "python",
  "expected": [
    { "file": "app/db/pool.py", "lines": [42, 43], "category": "resource-leak" }
  ]
}
```

`commit_date`, hafıza getirmede zamansal filtre için zorunludur. Bu tarihten sonra oluşmuş hata kartları kullanılamaz.
