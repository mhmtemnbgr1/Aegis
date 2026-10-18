# Değerlendirme (Benchmark)

Her örnek `dataset/<id>/` altında tutulur:

```
dataset/<id>/
├── diff.patch     # incelenecek değişiklik
└── labels.json    # beklenen bulgular
```

`labels.json` formatı:

```json
{
  "source": "injected | real-fix | synthetic-secret | clean",
  "language": "python",
  "expected": [
    { "file": "app/db.py", "line": 42, "category": "security", "severity": "critical" }
  ]
}
```

Sonuçlar `reports/` altına CSV ve grafik olarak yazılır (git'e eklenmez).
