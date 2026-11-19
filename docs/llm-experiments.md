# LLM deneylerini koşturma

Bu belge, Ollama'nın kurulu olduğu makinede RQ1 (ucuz LLM triage, #67) ve RQ2 (hafıza varyantları, #36) deneylerinin nasıl koşturulacağını anlatır. Hazırlık adımları (örneklem, diff'ler, hafıza getirme, LR ve sezgisel skorlar) yapıldı ve `eval/datasets/` altında sürümlendi. Koşu için **repo klonu, madencilik verisi ya da hafıza indeksi gerekmez**; yalnızca bu depo ve Ollama yeterli.

## Hazırlık

```bash
git pull
uv sync --extra ollama
ollama pull qwen2.5-coder:7b       # RQ2
ollama pull qwen2.5-coder:1.5b     # RQ1 ucuz triage
```

Ollama başka bir makinedeyse `OLLAMA_HOST=http://<adres>:11434` ortam değişkeni.

## RQ2 — hafızasız / plasebo / vektör / hibrit

600 commit (300 hatalı + 300 temiz, `eval/datasets/d2.jsonl`) × 4 varyant = 2.400 inceleme.

```bash
# 1) Kuru koşu: 12 commit × 4 varyant (~48 çağrı). Hata ya da bozuk JSON var mı bakın.
uv run python eval/rq2.py kos --model qwen2.5-coder:7b --limit 12
uv run python eval/rq2.py ozet --model qwen2.5-coder:7b

# 2) Tamamı. Yarıda kesilirse aynı komut kaldığı yerden sürer (tamamlananlar atlanır).
uv run python eval/rq2.py kos --model qwen2.5-coder:7b
uv run python eval/rq2.py ozet --model qwen2.5-coder:7b
```

- **İki test seti:** Varsayılan set (`--set revert`) hatalı örnek olarak tersine çevrilmiş gerçek düzeltmeleri kullanır; hatalı satırların yeri kesin bilinir. Gerçekçilik kontrolü için ikinci set (`--set szz`), SZZ'nin hatalı dediği gerçek commit'leri kullanır (etiketleri gürültülü). Temiz örnekler iki sette aynıdır; `szz` seti yalnızca 300 hatalı örneği koşturur (1.200 inceleme):

  ```bash
  uv run python eval/rq2.py kos --set szz --model qwen2.5-coder:7b
  uv run python eval/rq2.py ozet --set szz --model qwen2.5-coder:7b
  ```

  Önce ana seti bitirin; `szz` özeti temiz örneklerin sonuçlarını ana setten alır. Hafıza iki sette de aynı yönde fayda sağlıyorsa sonuç hem güvenilir hem gerçekçidir.
- **Varyantlar:** `none` hafızasız; `placebo` aynı sayıda ilgisiz kart (aynı repodan, commit'in dosyalarına dokunmayan); `vector` yalnızca LSA vektör araması; `hybrid` yapısal + BM25 + vektör (varsayılan). `--variants none,hybrid` ile seçilebilir; `structural` de vardır.
- **Risk sabit:** Her commit'e "orta" risk verilir; RQ2 gatekeeper'ı değil yalnızca hafızanın etkisini ölçer.
- **Süre tahmini:** 8 GB'lık bir NVIDIA ekran kartında çağrı başına ~10–20 sn; tamamı ~7–13 saat. İlerleme satırı ortalama süreyi gösterir. İkinci model (#36 "en az 2 LLM") için aynı komutlar `--model` değiştirilerek tekrarlanır.

## RQ1 — ucuz LLM triage

1.250 PR (RQ1 eğrisinin 25 penceresinin her birinden 50, `eval/datasets/rq1-triage.jsonl`). LLM'e yalnızca diff gösterilir ve 0–1 arası risk istenir; aynı PR'lardaki LR ve sezgisel skorlar dosyada hazırdır.

```bash
uv run python eval/rq1_triage.py kos --model qwen2.5-coder:1.5b --limit 25   # kuru koşu
uv run python eval/rq1_triage.py kos --model qwen2.5-coder:1.5b
uv run python eval/rq1_triage.py ozet --model qwen2.5-coder:1.5b
```

İsteğe bağlı: `--model qwen2.5-coder:7b` ile "büyük model triage" karşılaştırması.

## Sonuçları gönderme

Ham sonuçlar ve özetler `eval/results/` altına yazılır ve git'e girer:

```
eval/results/rq2/qwen2.5-coder_7b/results.jsonl, summary.md
eval/results/rq1-triage/qwen2.5-coder_1.5b/results.jsonl, summary.md
```

Koşu bitince bunları bir dalda commit'leyip PR açın. Uzun koşularda ara sonuçları da göndermek sorun değildir; özet her zaman ham sonuçlardan yeniden üretilir.

## Hazırlığı yeniden üretme (gerekmedikçe yapmayın)

Örneklemi değiştirmek tüm sonuçları geçersiz kılar. Madencilik verisi, hafıza indeksi ve klonların olduğu makinede:

```bash
aegis dataset --level d2                 # .aegis/data/d2.jsonl → eval/datasets/ altına kopyalanır
uv run python eval/rq2.py hazirla        # d2-memory.jsonl, d2-cards.jsonl
uv run python eval/rq1_triage.py hazirla # rq1-triage.jsonl
```
