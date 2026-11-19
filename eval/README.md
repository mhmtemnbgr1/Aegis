# Değerlendirme

Değerlendirme planı: [docs/presentation.md §5](../docs/presentation.md#5-değerlendirme-planı). LLM'siz sonuçlar: [docs/results.md](../docs/results.md).

```
eval/
├── datasets/
│   ├── d1.parquet, d1.json   # D1: SZZ etiketli commit özellikleri ve sürüm kaydı (RQ1)
│   ├── d1-report.md          # D1 repo seçimi ve sayılar
│   └── d2.jsonl, d2.json     # D2: hatalı + temiz commit'ler, diff'ler, beklenen satırlar (RQ2)
├── labels/                   # elle etiketleme örneklemleri ve sonuçları (#8, #9)
├── reports/                  # üretilen raporlar (git'e eklenmez)
└── *.py                      # deney ve analiz betikleri
```

## D1

Altı repodaki tüm commit'ler; Kamei, riskli yol, test oranı ve hafıza özellikleri ile SZZ etiketi. Üretim: `aegis dataset` (ayrıntı `d1-report.md`, şema `docs/mining-schema.md`).

## D2

Her D1 reposundan 50 hatalı ve 50 temiz commit (toplam 600). Üretim: `aegis dataset --level d2` (varsayılan tohum 0).

- **Hatalı:** SZZ'nin bug-inducing dediği commit. `expected`, bu hatayı sonradan düzelten fix'in sildiği satırların bu commit'teki yerleri (SZZ ile aynı süzgeçler). 1.343 satırın 1.342'si commit'in diff'inde eklenen satırdır.
- **Temiz:** SZZ'nin hiç suçlamadığı ve en yeni commit'ten en az 365 gün eski commit. Her bulgu yanlış alarmdır.
- **Tabakalama:** kaynak koduna eklenen satır sayısına göre 3 dilim (hatalı commit'lerin üçte birlikleri); iki sınıf aynı dilimlerden eşit sayıda örneklenir. Yalnız 3–300 satır ekleyen ve test dışı Python dosyasına dokunan commit'ler alınır.
- **Diff:** LLM'e verilecek değişiklik örneğin içindedir (yalnız kaynak dosyalar, `-U3`); deney için repo klonu gerekmez.
- **`after_cutoff`:** commit, LLM'in bilgi kesim tarihinden (varsayılan 2024-09-01, Qwen2.5-Coder) sonra mı (#55). D2'de yalnızca 17 örnek; kirlilik analizi için ayrı bir örneklem gerekir.

Satır biçimi (`d2.jsonl`, satır başına bir örnek):

```json
{
  "repo": "tqdm__tqdm",
  "sha": "ef653d81…",
  "parent": "…",
  "label": "buggy",
  "date": "2019-11-30T…+00:00",
  "size_bin": 0,
  "src_added": 6,
  "files": ["examples/tqdm_wget.py"],
  "diff": "diff --git a/examples/tqdm_wget.py …",
  "expected": [{"path": "examples/tqdm_wget.py", "line": 101}],
  "fix_shas": ["31d5b886…"],
  "after_cutoff": false
}
```

`date`, hafıza getirmede zamansal filtre için kullanılır: bu tarihten sonra düzeltilen hatalar hafızada görünmez.

## Betikler

| Betik | Ne üretir |
| --- | --- |
| `results.py` | `docs/results.md` (tüm LLM'siz sonuçlar, güven aralıkları, testler) |
| `rq1_curve.py` | RQ1 maliyet–recall eğrisi (PR düzeyi, kayan pencere) |
| `retrieval_eval.py` | RQ2 LLM'siz: hafıza getirme Recall@k ve MRR |
| `szz_variants.py` | SZZ süzgeçlerinin etiketli eşlemelerde ve veri miktarında etkisi |
| `labeling.py`, `agreement.py`, `tune_fix.py` | Etiket kalitesi örneklemleri ve uyum ölçümleri (#8, #9) |
