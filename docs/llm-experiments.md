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

## RQ2 yeniden koşusu (Kasım 2026) — adım adım

İlk RQ2 koşusunda (#121) bağlam penceresi ayarlanmamıştı. Ollama varsayılan pencereyi (2048 ya da 4096 token) aşan istemleri hata vermeden kesti; hafızalı varyantların istemleri uzun olduğu için çok daha sık kesildi (revert setinde `none` %6, `hybrid` %56). Bu yüzden RQ2 baştan koşulur. RQ1 triage sonuçları geçerlidir, **RQ1 yeniden koşulmaz**.

Kod artık bağlam penceresini kendisi ayarlar (16.384 token; sığmayan birkaç istem için 32.768), sıcaklığı 0 verir, her satıra kullanılan pencereyi yazar ve pencereyi dolduran yanıtı hata sayar. Bağlam penceresi kaydı olmayan eski satırlar otomatik yok sayılır. **Komutlara ayar eklenmez, dosya silinmez ya da taşınmaz.**

Bu adımları bir yapay zekâ asistanıyla yürütüyorsanız asistana bu bölümü olduğu gibi verin. Asistan kodu, veri setlerini, prompt'ları ya da ayarları değiştirmemeli; sonuç dosyalarını elle düzenlememelidir.

**0. Ollama ayarı (bir kez, her makinede).** Bellek kullanımını azaltan iki Ollama ayarı tüm koşu boyunca açık olur; 6 GB'lık ekran kartlarında modelin karta sığmasını sağlar. Windows'ta PowerShell'de:

```powershell
setx OLLAMA_FLASH_ATTENTION 1
setx OLLAMA_KV_CACHE_TYPE q8_0
```

Ardından Ollama'yı görev çubuğundaki simgesinden **Quit** ile tamamen kapatıp yeniden açın (ayar ancak yeniden başlatınca geçerli olur). Linux/macOS'ta aynı değişkenler `ollama serve` başlatılırken verilir.

**1. Depoyu güncelleyin:**

```bash
git checkout main
git pull
uv sync --extra ollama
ollama list            # qwen2.5-coder:7b görünmeli; yoksa: ollama pull qwen2.5-coder:7b
```

**2. Kuru koşu (~10–20 dk, 48 çağrı):**

```bash
uv run python eval/rq2.py kos --model qwen2.5-coder:7b --limit 12
```

Kontrol edin:

- Son satır `48 yeni koşu (48 hedef), 0 hata` gibi olmalı. Birkaç hata sorun değildir; yarısından fazlası hataysa **durun** ve hata mesajını bildirin.
- İlerleme satırlarında `ctx=16384` (bazen `ctx=32768`) görünmeli.
- `UYARI: model ekran kartına tam sığmadı` yazısı çıkarsa 0. adım uygulanmamış ya da Ollama yeniden başlatılmamış demektir; düzeltip devam edin. Uyarı yine de çıkıyorsa koşu geçerlidir, yalnızca yavaştır; devam edin ve PR'da belirtin.
- Art arda 10 hata olursa betik kendisi durur (`DURDU: ...`); genellikle Ollama kapalıdır. Ollama'yı açıp aynı komutu çalıştırın.

Kuru koşunun sonuçları tam koşuda tekrar kullanılır, silinmez.

**3. Ana set (~20 saat, 2.400 çağrı):**

```bash
uv run python eval/rq2.py kos --model qwen2.5-coder:7b
uv run python eval/rq2.py ozet --model qwen2.5-coder:7b
```

**4. Szz seti (~14 saat, 1.200 çağrı).** Ana set bitmeden başlamayın; szz özeti temiz örnekleri ana setten alır.

```bash
uv run python eval/rq2.py kos --set szz --model qwen2.5-coder:7b
uv run python eval/rq2.py ozet --set szz --model qwen2.5-coder:7b
```

Koşu yarıda kalırsa (elektrik, uyku, kapanma) **aynı komutu yeniden çalıştırın**; tamamlananlar atlanır, hatalılar yeniden denenir. Dizüstü bilgisayarda şarj kablosu takılı olmalı ve uyku kapalı olmalıdır. Bütün RQ2 aynı makinede koşulmalıdır.

**5. Sonuçları gönderin:**

```bash
git checkout -b results/rq2-rerun
git add eval/results/rq2 eval/results/rq2-szz
git commit -m "results: RQ2 rerun with a fixed context window"
git push -u origin results/rq2-rerun
```

PR açıklamasına yazın: makine ve ekran kartı, 0. adımın uygulanıp uygulanmadığı, uyarı çıkıp çıkmadığı, toplam süre, iki setin `ozet` çıktısındaki hata sayıları. Ana set bitince ara sonuç olarak gönderilebilir.

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
