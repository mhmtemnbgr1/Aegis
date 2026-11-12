# Madencilik Çıktı Şeması

`aegis mine <repo>` komutu, repo başına `<data_dir>/<slug>/` dizinine (varsayılan `.aegis/data/`) aşağıdaki dosyaları yazar. Slug, uzak adresten `owner__name` biçiminde türetilir (ör. `tqdm__tqdm`, `httpie__cli`). Şema sürümü: **1** (`aegis.mining.schema.SCHEMA_VERSION`).

```bash
aegis mine https://github.com/tqdm/tqdm           # .aegis/repos/ altına klonlar ve tarar
aegis mine ../tqdm --since 2021-01-01             # yerel klon, tarih sınırıyla
aegis mine ../tqdm --no-functions                 # fonksiyon çıkarımı olmadan (daha hızlı)
GITHUB_TOKEN=... aegis mine ../tqdm --issue-labels  # bağlı issue etiketleriyle fix tespiti
aegis mine ../tqdm --szz-only --szz-variant b     # taramayı atla, yalnızca SZZ'yi yeniden çalıştır
```

Tarama bittikten sonra SZZ otomatik çalışır (`--no-szz` ile kapatılır).

Commit'ler HEAD'den erişilebilen geçmişten, eskiden yeniye taranır. Varsayılan olarak geçmişin tamamı taranır, çünkü deneyim ve geçmiş metrikleri (#10) eski commit'lere ihtiyaç duyar. `history_years` sınırı SZZ adımında uygulanır (#9).

## `commits.parquet`

Commit başına bir satır.

| Sütun | Tip | Açıklama |
| --- | --- | --- |
| `repo` | string | Repo slug'ı |
| `sha` | string | Commit SHA'sı |
| `parents` | list[string] | Ebeveyn SHA'ları; ilk commit'te boş |
| `is_merge` | bool | Birden fazla ebeveyn varsa `true` |
| `author_name`, `author_email` | string | Yazar |
| `author_date` | datetime (UTC, µs) | Yazım zamanı |
| `author_utc_offset_minutes` | int32 | Yazarın saat dilimi, UTC'ye göre dakika (ör. +03:00 → 180) |
| `committer_date` | datetime (UTC, µs) | Commit zamanı |
| `message` | string | Commit mesajının tamamı |
| `files_changed` | int32 | Değişen dosya sayısı (merge commit'lerinde 0) |
| `lines_added`, `lines_deleted` | int32 | Dosyalar üzerinden toplam eklenen ve silinen satırlar |
| `is_fix` | bool | Fix commit'i mi (aşağıya bakın) |
| `fix_signals` | list[string] | Karara giren sinyaller |
| `linked_issues` | list[int64] | Mesajda geçen `#N` / `GH-N` numaraları (başka repo referansları hariç) |

**Merge commit'leri:** `is_merge = true` olarak işaretlenir. PyDriller merge commit'lerinin dosya değişikliklerini döndürmez, çünkü bu değişiklikler dallardaki commit'lerde zaten görülür. Bu yüzden `files.parquet` dosyasında merge commit'lerine ait satır yoktur. Merge commit'leri hiçbir zaman fix sayılmaz.

### Fix tespiti (`is_fix`, `fix_signals`)

Kalıplar `.aegis.toml` dosyasının `[mining]` bölümünden ayarlanır (`fix_patterns`, `fix_exclude_patterns`, `bug_labels`). Bir commit şu iki durumdan birinde fix sayılır:

1. Mesajın tamamı bir `fix_patterns` kalıbıyla eşleşir ve **ilk satırı** bir `fix_exclude_patterns` kalıbıyla eşleşmez.
2. Bağlı issue'lardan biri `bug_labels` listesindeki bir etiketi taşır. Bu durumda dışlama kalıbı yok sayılır. Etiketler yalnızca `--issue-labels` verildiğinde GitHub'dan okunur ve `issue_labels.json` dosyasında cache'lenir.

`closes #N` gibi kapatma ifadeleri tek başına fix sayılmaz, çünkü kapatılan issue bir özellik isteği de olabilir. Bu ifadeler `closes:N` sinyali olarak kaydedilir.

| Sinyal | Anlamı |
| --- | --- |
| `keyword:<eşleşme>` | Bir fix kalıbı eşleşti |
| `excluded:<eşleşme>` | Bir dışlama kalıbı ilk satırda eşleşti |
| `label:<etiket>#<N>` | Bağlı issue N bir hata etiketi taşıyor |
| `closes:<N>` | Kapatma ifadesi (`closes/fixes/resolves #N`) |
| `merge` | Merge commit'i (fix sayılmaz) |

## `files.parquet`

Commit × değişen dosya. Yollar `/` ayraçlıdır.

| Sütun | Tip | Açıklama |
| --- | --- | --- |
| `repo`, `sha` | string | Commit |
| `old_path` | string? | Önceki yol; eklenen dosyada `null` |
| `new_path` | string? | Yeni yol; silinen dosyada `null` |
| `change_type` | string | `ADD`, `DELETE`, `MODIFY`, `RENAME`, `COPY`, `UNKNOWN` |
| `lines_added`, `lines_deleted` | int32 | Dosyadaki eklenen ve silinen satırlar |
| `is_python` | bool | Yol `.py` ile bitiyorsa `true` |

## `functions.parquet`

Commit × değişen Python fonksiyonu (lizard ile). Değişen satırlarla kesişen ya da yeni eklenen fonksiyonlar yer alır. `--no-functions` verildiğinde boş kalır.

| Sütun | Tip | Açıklama |
| --- | --- | --- |
| `repo`, `sha` | string | Commit |
| `path` | string | Dosya yolu |
| `name` | string | Fonksiyon adı; lizard metotlarda sınıf adını vermez, sınıf `path` + satır aralığından bulunur |
| `long_name` | string | İmzayla birlikte ad |
| `start_line`, `end_line` | int32 | Commit sonrası (silinmişse öncesi) satır aralığı |
| `nloc` | int32 | Yorum ve boşluk dışındaki satırlar |
| `complexity` | int32 | Döngüsel karmaşıklık |

## `szz.parquet`

Fix × bug-inducing commit × dosya. SZZ, pyszz PyPI'da bulunmadığı için `git diff -U0` ve `git blame --porcelain` üzerine kurulu kendi uygulamamızdır (`aegis.mining.szz`).

| Sütun | Tip | Açıklama |
| --- | --- | --- |
| `repo` | string | Repo slug'ı |
| `fix_sha` | string | Fix commit'i |
| `inducing_sha` | string | Silinen/değiştirilen satırları son değiştiren commit |
| `path` | string | Fix'in ebeveynindeki dosya yolu |
| `blamed_lines` | int32 | Bu dosyada bu commit'e izlenen satır sayısı |
| `fix_date`, `inducing_date` | datetime (UTC) | Yazım zamanları |

Bir fix şu koşullarda işlenir:
- `is_fix` doğru olmalı ve merge commit'i olmamalı.
- Repodaki en yeni commit'ten geriye son `history_years` (varsayılan 5) yıl içinde olmalı.
- En fazla `max_files_per_commit` (varsayılan 50) dosya değiştirmiş olmalı.

Blame yalnızca **kaynak dosyalarda** yapılır. Kaynak dosya, uzantısı `source_extensions` listesinde olan ve `test_path_patterns` ile eşleşmeyen dosyadır. Bu sayede yalnızca testlere, CI'a ya da dokümana dokunan "fix"ler eşleme üretmez. Sınıflandırıcının bu tür gürültüsünün büyük kısmı burada elenir. Aday commit'lerden şunlar elenir:
- merge commit'leri
- fix'ten sonra yazılmış commit'ler
- taranan geçmişin dışında kalan commit'ler

| Varyant | Davranış |
| --- | --- |
| `ma` (varsayılan) | MA-SZZ'ye yakın. Diff ve blame boşluk değişikliklerini yok sayar (`-w`). Boş satırlar, `#` yorumları ve **docstring** satırları (ast ile bulunur) blame edilmez. `max_files_per_commit`'i aşan toplu commit'ler `--ignore-revs-file` ile atlanır, böylece blame bu commit'lerin ardındaki asıl commit'e ulaşır. |
| `b` | Düz B-SZZ: düz diff, düz blame. |

`szz_meta.json` dosyasına şunlar yazılır: kullanılan varyant, `history_years`, kesim tarihi, atlanan fix sayıları (çok büyük / kaynak dosyasız) ve sonuç sayıları.

**Elle kontrol (#9):** `aegis.mining.szz.review_sample(data_dir, n=50)` fonksiyonu rastgele 50 eşleme seçer ve `eval/labels/szz-<slug>.csv` dosyasına yazılır. Her satırda iki commit'in GitHub bağlantısı bulunur. Kontrol eden kişi `correct` sütununa `evet`, `hayir` ya da `belirsiz` yazar. Hata oranı bu sütundan hesaplanır.

## `kamei.parquet`

Merge olmayan her commit için Kamei vd. (2013) tarafından tanımlanan 14 değişiklik metriği (`aegis.features.kamei`). Metrikler tarama bittiğinde hesaplanır. Ek git çağrısı gerekmez; scrapy'de 2 saniye sürer.

| Sütun | Açıklama |
| --- | --- |
| `repo`, `sha` | Commit |
| `as_of` | Metriklerin hesaplandığı an: commit'in **commit zamanı** (UTC) |
| `ns`, `nd`, `nf` | Değişen alt sistem (en üst dizin), dizin ve dosya sayısı |
| `entropy` | Değişen satırların dosyalara dağılımı, −Σ pᵢ log₂ pᵢ (bit; normalleştirilmemiş) |
| `la`, `ld` | Eklenen / silinen satırlar |
| `lt` | Değişen dosyaların değişiklikten önceki toplam satır sayısı (yeni dosyalar 0) |
| `fix` | `is_fix` (0/1) |
| `ndev` | Değişen dosyalara daha önce dokunan farklı geliştirici sayısı |
| `age` | Değişen dosyaların son değişikliğinden bu yana ortalama gün (geçmişi olmayan dosyalar hariç) |
| `nuc` | Değişen dosyalara daha önce dokunan farklı commit sayısı |
| `exp` | Geliştiricinin önceki commit sayısı |
| `rexp` | Yıla göre ağırlıklı deneyim: n tam yıl önceki commit 1/(n+1) sayılır |
| `sexp` | Geliştiricinin değişen alt sistemlere dokunan önceki commit sayısı |

Tüm metrikler `float64` tipindedir. Geliştirici kimliği, küçük harfe çevrilmiş e-posta adresidir.

### Zaman kuralı (`as_of`, FR-18)

Her özellik fonksiyonu `(change, history, *, as_of)` imzasını taşır (`aegis.features.Feature`). Geçmişi yalnızca `ChangeHistory` üzerinden okur. Bu sınıf, bir olayı ancak **commit zamanı `as_of`'tan kesinlikle önce** ise döndürür:

- Bir commit'in metrikleri kendisini ve sonraki commit'leri göremez.
- Aynı saniyede commit'lenmiş commit'ler (ör. rebase ile toplu olarak eklenenler) birbirini görmez. Bu durumda bazı bilgiler eksik kalır, ama gelecekten veri sızmaz.
- Yazım zamanı yerine commit zamanı kullanılır. Rebase edilmiş, yazım tarihi eski görünen bir commit, repoya girdiği andan önce görünmez.
- Yeniden adlandırma geçmişi taşımaz. Yeni yola, zaman damgalı bir "önceki yol" bağlantısı eklenir ve sorgu bu bağlantıyı yalnızca adlandırma `as_of`'tan önce gerçekleştiyse izler. Böylece gelecekteki bir adlandırma geçmiş sorguların sonucunu değiştirmez.

`lt` ve `age` gibi geçmiş metrikleri git'ten okunmaz. Dosya değişiklikleri kronolojik sırayla yeniden oynatılarak hesaplanır. Merge commit'leri dosya değişikliği taşımadığı için olay üretmez. Bu yüzden merge sırasında yapılan çakışma çözümleri satır sayısına yansımaz. Bu, bilinçli olarak kabul edilmiş küçük bir yaklaşıklıktır.

Testler (`tests/test_features.py`): 14 metriğin her biri elle hesaplanmış bir örnekle doğrulanır. Ayrıca geleceğe tarihli commit'ler ve adlandırmalar eklendiğinde mevcut commit'lerin metriklerinin değişmediği hem bellekte hem gerçek bir git deposunda test edilir.

İlk gözlem: SZZ'nin bug-inducing olarak işaretlediği commit'ler belirgin şekilde daha büyük ve daha dağınıktır. scrapy'de medyan `la` 47'ye karşı 7, ortalama `entropy` 1,46'ya karşı 0,59, medyan `ndev` 27'ye karşı 7. Bu, Kamei'nin bulgularıyla tutarlıdır.

## `meta.json`

Veri sürümü kaydı (NFR-04): şema ve Aegis sürümü, `mined_at`, `remote_url`, taranan `head_sha`, `since`, kullanılan `mining_config`, satır sayıları ve süre. Aynı `head_sha` ve `mining_config` ile yapılan tarama aynı veriyi üretir.

## Pilotlar (13 Kasım 2026)

### tqdm

| Ölçüm | Değer |
| --- | --- |
| Commit | 2.132 (310 merge) |
| Fix (yalnızca mesaj kalıpları) | 482 (merge dışındakilerin %26'sı) |
| Dosya / fonksiyon değişikliği | 3.644 / 4.877 |
| Süre | 152 sn (Ryzen 7 6800H, fonksiyonlar dahil) |
| Klon / Parquet boyutu | 7,7 MB / 0,33 MB |

Örneklemde görülen başlıca hata türü: test, CI ve kapsam düzeltmeleri de (`tests: fix coverage`, `fix pytest deprecation warning`) fix sayılıyor. Kalıplar, 200 örneklik doğrulama seti (#8) ölçülmeden ayarlanmamalı. Bu fix'ler SZZ'de kaynak dosyası olmadığı için zaten eleniyor.

SZZ (son 5 yıl, kesim 2021-09-11):

| | `ma` | `b` |
| --- | --- | --- |
| Penceredeki fix | 71 | 71 |
| Kaynak dosyasız (elendi) | 25 | 25 |
| Eşlenen fix | 36 | 39 |
| Bug-inducing commit | 72 | 131 |
| Fix–inducing çifti | 86 | 150 |
| Süre | 7 sn | 5 sn |

Docstring filtresi eklenmeden önce `ma` 125 inducing commit üretiyordu. Farkın büyük kısmı, 4 issue'yu kapatan ve çoğunlukla docstring değiştiren tek bir özellik commit'inden geliyordu. tqdm'in son 5 yılda ürettiği 72 inducing commit, D1'deki 200 sınırının altında kalıyor (#13). tqdm pilot olarak kalıyor; D1 için yedek repo ya da daha uzun bir pencere gerekiyor.

### scrapy (en büyük hedef repo, #9 süre ölçümü)

| Ölçüm | Değer |
| --- | --- |
| Commit | 11.764 (2.123 merge) |
| Fix (yalnızca mesaj kalıpları) | 1.321 |
| Dosya / fonksiyon değişikliği | 30.661 / 62.035 |
| Tarama süresi | 780 sn (~13 dk, fonksiyonlar dahil) |
| SZZ (`ma`, 5 yıl, kesim 2021-11-12) | 321 fix → 202 eşlendi · **637 bug-inducing commit** · 949 çift |
| SZZ süresi | 72 sn |
| Atlanan fix | 1 çok büyük, 91 kaynak dosyasız |
| Klon / Parquet boyutu | 45 MB / 2,4 MB |

Toplam süre ~14 dk. Darboğaz taramadır (PyDriller diff + lizard); SZZ küçük kalır. scrapy, D1 için gereken 200 inducing sınırını rahatça aşıyor.
