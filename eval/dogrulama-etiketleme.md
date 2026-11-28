# Doğrulama seti etiketleme yönergesi (#108)

Önceki kontroller küçüktü: 48 SZZ eşlemesi (`eval/labels/szz-kontrol.csv`) ve D2'den 102 örnek (`eval/labels/d2-kontrol.csv`). Bu set, modelin gerçekten hatalı commit'leri ne kadar iyi bulduğunu ölçmek ve temiz etiketle eğitimi (#109) değerlendirmek için ~270 yeni örnek ekler.

## Örneklem

`eval/labels/dogrulama-sample.csv`: 6 D1 reposundan (black, luigi, sanic, scrapy, tornado, tqdm) tabakalı, sabit tohumlu (108), karışık sıralı 270 örnek. Daha önce kontrol edilen örnekler dışarıda bırakıldı. Üretim: `uv run python eval/label_set.py ornekle`.

| Tür | Repo başına | Toplam | Kaynak | Soru |
| --- | --- | --- | --- | --- |
| SZZ eşlemesi | 25 | 150 | D1'in hatalı commit'leri; her biri için rastgele bir düzelten commit | Bu commit, düzelten commit'in giderdiği hatayı gerçekten getiriyor mu? |
| Düzeltme | 10 | 60 | D2'nin tersine çevrilmiş düzeltmeleri (`revert: true`) | Bu commit gerçekten bir hata düzeltmesi mi? |
| Temiz | 10 | 60 | D2'nin temiz commit'leri | Değişiklikte açık bir hata var mı? |

## Nasıl etiketlenir

1. `eval/labels/dogrulama-review.html` dosyasını tarayıcıda açın (tek dosya; internet gerekmez, GitHub bağlantıları isteğe bağlı). Sayfa `uv run python eval/label_set.py sayfa` ile üretilir.
2. Üstteki **Set no** alanına set numaranızı yazın (`3` ya da `4`).
3. Her örnek için bir seçenek işaretleyin ve **gerekçeyi bir cümleyle** not alanına yazın. Kararlar tarayıcıda saklanır; sayfayı kapatıp sonra devam edebilirsiniz.
4. Bitince **CSV indir** ile `etiket-seti-<n>.csv` dosyasını alın ve `eval/labels/` altına koyun.

**İki etiket seti birbirinden bağımsız hazırlanır.** Bitene kadar setler karşılaştırılmaz.

## Seçenekler

**SZZ eşlemesi.** Sayfada düzelten commit'in (FIX) sildiği satırlar ve bu satırların hatayı getirdiği söylenen commit'teki (INDUCING) hali gösterilir; ilgili satırlar ▶ ile işaretlidir.

| Seçenek | Ne zaman |
| --- | --- |
| **Doğru** | INDUCING, FIX'in giderdiği hatalı mantığı yazdı ve işaretli satırlar hatanın yeri. |
| **Kısmen** | Hatayı INDUCING getirdi ama işaretli satırlar hatanın yerini eksik ya da fazla gösteriyor. |
| **Yanlış** | Satırlar yalnızca biçimlenmiş, taşınmış ya da yeniden adlandırılmış; hata INDUCING'den önce de vardı; ya da FIX aslında hata düzeltmesi değil. |
| **Belirsiz** | 3 dakikada karar veremiyorsanız. |

**Düzeltme.** Commit mesajı ve değişikliği gösterilir.

| Seçenek | Ne zaman |
| --- | --- |
| **Evet** | Yanlış çıktı, çökme, istisna, sızıntı, regresyon, yanlış koşul gibi üretim kodundaki bir hatayı düzeltiyor (testle gelmesi fark etmez). |
| **Hayır** | Yeni özellik, yeniden düzenleme, performans; yalnızca doküman, yazım hatası, test, CI, biçim ya da bağımlılık güncellemesi. |
| **Belirsiz** | Mesaj ve diff'ten karar veremiyorsanız. |

**Temiz.** Commit mesajı ve değişikliği gösterilir.

| Seçenek | Ne zaman |
| --- | --- |
| **Temiz** | Değişiklikte bir hata görmüyorsunuz. |
| **Hata** | Diff'ten açıkça görülen bir hata var (yanlış koşul, eksik kontrol, kaynak sızıntısı, yanlış çağrı vb.). |
| **Belirsiz** | Karar veremiyorsanız. |

İpuçları: örnek başına 1–3 dakika yeterli (tüm set ~5–7 saat; birkaç oturuma bölünebilir). Emin olmadığınız stil ya da tasarım tercihleri hata değildir.

## Uyum, son etiketler ve sonuç

```bash
uv run python eval/label_set.py uyum eval/labels/etiket-seti-3.csv eval/labels/etiket-seti-4.csv
uv run python eval/label_set.py birlestir eval/labels/etiket-seti-3.csv eval/labels/etiket-seti-4.csv
uv run python eval/label_set.py sonuc
```

- `uyum`: tür başına aynı cevap oranı ve Cohen κ, farklı cevaplı örneklerin listesi.
- `birlestir`: iki setin aynı cevabı verdiği örnekler `eval/labels/dogrulanmis.csv` dosyasına yazılır (farklı cevaplılar girmez). `label` sütunu #109 içindir: SZZ eşlemesinde **Doğru**/**Kısmen** → `buggy`; temizde **Temiz** → `clean`, **Hata** → `buggy`; diğerleri boş (SZZ **Yanlış** commit'in temiz olduğunu göstermez, başka bir hatayı getiriyor olabilir).
- `sonuc`: tür başına doğruluk ve SZZ'nin repo bazında doğruluğu (%95 Wilson GA, belirsizler hariç), `docs/mining-schema.md` ve `eval/README.md` için Markdown.
