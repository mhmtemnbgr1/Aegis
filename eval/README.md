# Değerlendirme

Değerlendirme planı: [docs/presentation.md §5](../docs/presentation.md#5-değerlendirme-planı). LLM'siz sonuçlar: [docs/results.md](../docs/results.md).

```
eval/
├── datasets/
│   ├── d1.parquet, d1.json   # D1: SZZ etiketli commit özellikleri ve sürüm kaydı (RQ1)
│   ├── d1-report.md          # D1 repo seçimi ve sayılar
│   ├── d2.jsonl, d2.json     # D2: hatalı + temiz commit'ler, diff'ler, beklenen satırlar (RQ2)
│   ├── d2-memory.jsonl       # D2 örneği × hafıza varyantı → kart kimlikleri (eval/rq2.py hazirla)
│   ├── d2-cards.jsonl        # bu kartların prompt'a giren alanları
│   ├── d2-szz*.jsonl         # ikinci RQ2 seti: SZZ'li hatalı örnekler ve hafızaları (gerçekçilik kontrolü)
│   └── rq1-triage.jsonl      # RQ1 triage örneklemi: PR diff'leri, LR ve sezgisel skorlar
├── results/                  # LLM deneylerinin ham sonuçları ve özetleri (git'e girer)
├── labels/                   # elle etiketleme örneklemleri ve sonuçları (#8, #9)
├── reports/                  # üretilen raporlar (git'e eklenmez)
└── *.py                      # deney ve analiz betikleri
```

## D1

Altı repodaki tüm commit'ler; Kamei, riskli yol, test oranı ve hafıza özellikleri ile SZZ etiketi. Üretim: `aegis dataset` (ayrıntı `d1-report.md`, şema `docs/mining-schema.md`).

## D2

Her D1 reposundan 50 hatalı ve 50 temiz commit (toplam 600). Üretim: `aegis dataset --level d2` (varsayılan tohum 0).

- **Hatalı (tersine çevrilmiş düzeltme):** başlığında düzeltme anahtar kelimesi geçen gerçek bir fix tersine çevrilir; diff, düzeltilmiş koddan hatalı koda gider (`revert: true`, `sha` = fix, `parent` = fix'in ebeveyni). `expected`, fix'in sildiği ve diff'te yeniden eklenen satırlar (yorum, import, docstring hariç). SZZ eşlemesi kullanılmaz: etiket doğruluğu yalnızca fix tespitine bağlıdır (başlık kuralıyla %96). Medyan 2 satırlık küçük değişiklikler.
- **Neden SZZ değil:** SZZ eşlemelerinin elle kontrolde yalnızca %19–31'i hatayı gerçekten getiriyordu. SZZ'li hatalı örnekler gerçekçilik kontrolü için ikinci set olarak tutulur (`d2-szz.jsonl`, `aegis dataset --level d2 --buggy szz`; `eval/rq2.py --set szz`).
- **Temiz:** SZZ'nin hiç suçlamadığı ve en yeni commit'ten en az 365 gün eski commit. Her bulgu yanlış alarmdır.
- **Tabakalama:** her sınıf kendi boyut dağılımının üçte birlik dilimlerinden eşit sayıda örneklenir. Temiz commit'ler 3–300 satır ekler (medyan 19), tersine çevrilmiş düzeltmeler çok daha küçüktür. Bu yüzden hatalı ve temiz örneklerin mutlak oranları birbiriyle karşılaştırılmaz; RQ2 varyantları her sınıf içinde eşleştirilerek karşılaştırılır.
- **Bilinen etki:** tersine çevrilmiş diff'te silinen satırlar düzeltilmiş kodun kendisidir; bu, tespiti kolaylaştırabilir. Tüm hafıza varyantları aynı diff'i gördüğü için hafızanın etkisi ölçümü bundan etkilenmez.
- **Diff:** LLM'e verilecek değişiklik örneğin içindedir (yalnız kaynak dosyalar, `-U3`); deney için repo klonu gerekmez.
- **`after_cutoff`:** commit, LLM'in bilgi kesim tarihinden (varsayılan 2024-09-01, Qwen2.5-Coder) sonra mı (#55). D2'de 35 hatalı örnek; keşif amaçlı.

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

**SZZ doğrulaması (#69):** İlk SZZ örnekleminden 102 örnek iki etiket setiyle kontrol edildi (`labels/d2-kontrol-1.csv`, `-2.csv`; uyum κ 0,68 hatalı, 0,45 temiz). Ortak etiketlerde 10 hatalı SZZ örneği ve 33 temiz örnek doğrulandı; bu alt küme yalnızca `--set szz` sonuçlarında kullanılır. Varsayılan revert seti için ayrı bir 102 örnekli inceleme hazırlanır (`d2-etiketleme.md`); eski SHA'lar yeni sete aktarılmaz.

## Betikler

| Betik | Ne üretir |
| --- | --- |
| `results.py` | `docs/results.md` (tüm LLM'siz sonuçlar, güven aralıkları, testler) |
| `rq1_curve.py` | RQ1 maliyet–recall eğrisi (PR düzeyi, kayan pencere) |
| `retrieval_eval.py` | RQ2 LLM'siz: hafıza getirme Recall@k ve MRR |
| `rq2.py` | RQ2 LLM deneyi: hazırlık, koşu, özet (`docs/llm-experiments.md`) |
| `rq1_triage.py` | RQ1 ucuz LLM triage: hazırlık, koşu, özet |
| `szz_variants.py` | SZZ süzgeçlerinin etiketli eşlemelerde ve veri miktarında etkisi |
| `labeling.py`, `agreement.py`, `tune_fix.py` | Etiket kalitesi örneklemleri ve uyum ölçümleri (#8, #9) |
