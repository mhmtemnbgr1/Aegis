# D2 etiketleme yönergesi (#69)

D2'nin varsayılan `revert` setinde hatalı örnekler gerçek düzeltmelerin tersine çevrilmesidir. Bu örnekler için ayrı bir insan doğrulama seti hazırlanır ve RQ2 özetinde yalnızca bu set kullanılır. İlk SZZ örneklemi üzerindeki eski etiketleme SZZ gerçekçilik kontrolüne (`--set szz`) aittir; eski SZZ SHA'ları tersine çevrilmiş düzeltmelere uygulanmaz.

## Örneklem

`eval/labels/d2-revert-sample.csv`: güncel revert D2 setinden her repoya 10 hatalı ve 7 temiz commit, toplam 102 örnek (sabit tohum, karışık sıra). Üretim: `uv run python eval/d2_labeling.py ornekle`. Önceki SZZ örneklemi ve etiket CSV'leri arşiv olarak korunur; üzerine yazılmaz.

## Nasıl etiketlenir

1. `uv run python eval/d2_labeling.py sayfa` ile üretilen `eval/labels/d2-revert-review.html` dosyasını tarayıcıda açın (tek dosya; internet gerekmez, GitHub bağlantıları isteğe bağlı).
2. Üstteki **Ad** alanına benzersiz adınızı yazıp **Bu adla devam et** düğmesine basın. Yanıtlar ada göre ayrı saklanır; iki değerlendirici aynı tarayıcıyı kullansa da yanıtlar karışmaz.
3. Her örnek için bir seçenek işaretleyin. Kararlar tarayıcıda saklanır; sayfayı kapatıp sonra aynı adla devam edebilirsiniz.
4. Bitince **CSV indir** ile `d2-revert-kontrol-<ad>.csv` dosyasını alın ve `eval/labels/` altına koyun.

**İki etiket seti birbirinden bağımsız hazırlanır.** Bitene kadar setler karşılaştırılmaz.

## Seçenekler

**Hatalı (revert) örnekler.** Sayfada gerçek bir düzeltmenin tersine çevrilmiş diff'i gösterilir. Koyu yeşil satırlar düzeltmenin geri aldığı satırlardır; özgün düzeltme de karşılaştırma için gösterilir. Bu örneklerin makul bir hatayı yeniden oluşturup oluşturmadığını ve vurgulanan satırların hatayı gösterip göstermediğini değerlendirin.

| Seçenek | Ne zaman |
| --- | --- |
| **Doğru** | Commit, düzelten commit'in giderdiği hatayı gerçekten getiriyor ve koyu yeşil satırlar hatanın yerini gösteriyor. |
| **Kısmen** | Commit hatayı getiriyor ama koyu yeşil satırlar hatanın yerini eksik ya da fazla gösteriyor (ör. asıl hatalı satır vurgulu değil). |
| **Yanlış** | Hata bu commit'ten gelmiyor: satır yalnızca biçimlenmiş, taşınmış, yeniden adlandırılmış ya da hata zaten vardı. Ya da düzelten commit aslında hata düzeltmesi değil (yeni özellik, tip ekleme, temizlik). |
| **Belirsiz** | 3 dakikada karar veremiyorsanız. |

**Temiz örnekler.** Yalnızca commit'in değişikliği gösterilir.

| Seçenek | Ne zaman |
| --- | --- |
| **Temiz** | Değişiklikte bir hata görmüyorsunuz. |
| **Hata** | Diff'ten açıkça görülen bir hata var (yanlış koşul, eksik kontrol, kaynak sızıntısı, yanlış çağrı vb.). Notta kısaca yazın. |
| **Belirsiz** | Karar veremiyorsanız. |

İpuçları:

- Örnek başına 1–3 dakika yeterli; tüm set yaklaşık 2–3 saat.
- Emin olmadığınız stil ya da tasarım tercihleri hata değildir.
- GitHub bağlantısı commit'in tamamını gösterir; gerekirse bakın.

## Uyum ve son etiketler

```bash
uv run python eval/d2_labeling.py uyum eval/labels/d2-revert-kontrol-<a>.csv eval/labels/d2-revert-kontrol-<b>.csv
```

Komut, hatalı ve temiz örnekler için ayrı ayrı Cohen κ'yı ve farklı cevaplı örnekleri yazar. Son etiketler yalnızca iki setin aynı cevabı verdiği örneklerden oluşur:

```bash
uv run python eval/d2_labeling.py birlestir eval/labels/d2-revert-kontrol-1.csv eval/labels/d2-revert-kontrol-2.csv
```

Sonuç `eval/labels/d2-revert-kontrol.csv` (`labeler` = `ortak`). RQ2'nin varsayılan `revert` özeti yalnızca bu SHA'ları kullanır. Tarihsel `d2-kontrol.csv` eski SZZ örnekleminin etiketidir; yalnızca `eval/rq2.py ozet --set szz` bunu kullanır.

## Önceki SZZ örneklemi sonucu (19 Kasım 2026)

| Tür | Aynı cevap | Cohen κ |
| --- | --- | --- |
| Hatalı (SZZ) | 52/60 | 0,68 |
| Temiz | 36/42 | 0,45 |

İki setin ortak olduğu 88 örnek: hatalı commit'lerde 6 doğru, 4 kısmen, 42 yanlış; temiz commit'lerde 33 temiz, 3 hata. SZZ'nin "hatalı" dediği commit'lerin ortak cevaplı olanlarının yalnızca 10/52'si (%19) hatayı gerçekten getiriyor; bu, 50 eşlemelik ilk kontroldeki %31 ile aynı yönde. Doğrulanmış alt küme: 10 hatalı + 33 temiz commit.
