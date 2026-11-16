# D1 veri seti madencilik raporu

**Üretim tarihi:** 2026-11-14 20:44 UTC  
**Aegis:** `0.0.1` · **Şema:** `1` · **SZZ:** MA-SZZ  
**Eşik:** repo başına en az 200 bug-inducing commit

D1, BugsInPy'de bulunan altı açık kaynak Python projesinin gerçek Git geçmişlerinden üretildi; sentetik veya mock satır kullanılmadı. Taranan her repo'nun HEAD SHA'sı `d1.json` manifestinde kayıtlıdır. Parquet, commit SHA/tarihi, sayısal özellikler, SZZ tabanlı `buggy` etiketi ve etiketin bilindiği `fixed_at` zamanını içerir; kaynak kod diff'leri ve commit mesajları alınmamıştır.

`mem_func_bugs` ve `mem_file_bugs` sütunları bu D1 üretiminde sıfırdır; bug-memory kartları bu issue'nun veri çıkarım kapsamına dahil değildir.

## Dahil edilen depolar

| Repo | Commit satırı | Fix | Bug-inducing | Pozitif oran | Kaynak lisansı |
| --- | ---: | ---: | ---: | ---: | --- |
| [psf/black](https://github.com/psf/black) | 2.507 | 544 | 390 | %15,6 | MIT |
| [sanic-org/sanic](https://github.com/sanic-org/sanic) | 2.112 | 390 | 505 | %23,9 | MIT |
| [scrapy/scrapy](https://github.com/scrapy/scrapy) | 9.630 | 1.141 | 1.139 | %11,8 | BSD-3-Clause |
| [spotify/luigi](https://github.com/spotify/luigi) | 3.047 | 543 | 595 | %19,5 | Apache-2.0 |
| [tornadoweb/tornado](https://github.com/tornadoweb/tornado) | 4.148 | 661 | 575 | %13,9 | Apache-2.0 |
| [tqdm/tqdm](https://github.com/tqdm/tqdm) | 1.821 | 400 | 395 | %21,7 | MIT |
| **Toplam** | **23.265** | **3.679** | **3.599** | **%15,5** | — |

Parquet `d1.parquet`, makinece okunabilir sürüm manifesti `d1.json` içindedir. Manifest her repo için HEAD SHA, SZZ çeşidi, etiket kesim tarihi ve sayımları içerir. Parquet SHA-256: `d4d6af1c000f57abc28ffe93dbb3766a517d88546f17332e3b7ce5f41c79fa32`.

## Eşiğin altında kalan adaylar

| Repo | Bug-inducing | Karar |
| --- | ---: | --- |
| [fastapi/fastapi](https://github.com/fastapi/fastapi) | 138 | Luigi ile değiştirildi |
| [httpie/cli](https://github.com/httpie/cli) | 167 | Sanic ile değiştirildi; HTTPie demo fork'u olarak kaldı |
| [cookiecutter/cookiecutter](https://github.com/cookiecutter/cookiecutter) | 156 | Yedek denendi, eşik altı |
| [nvbn/thefuck](https://github.com/nvbn/thefuck) | 149 | BugsInPy adayı olarak denendi, eşik altı |

`spotify/luigi` 595 pozitif ile FastAPI'nin yerini aldı. Cookiecutter ve `thefuck` eşiği geçmedi. `sanic-org/sanic` 505 pozitif ile HTTPie'nin yerini aldı. `psf/requests` 354 pozitif üretse de BugsInPy kapsamına girmediği için seçim kriterini korumak amacıyla nihai altılıya eklenmedi.

## Yeniden üretme

Seçilen altı repo'nun madencilik çıktıları `.aegis/data/<owner>__<repo>/` altında olduktan sonra yalnızca bu klasörleri `.aegis/d1-qualified/` altına kopyalayın ve çalıştırın:

```powershell
$selected = @('psf__black', 'sanic-org__sanic', 'scrapy__scrapy', 'spotify__luigi', 'tornadoweb__tornado', 'tqdm__tqdm')
New-Item -ItemType Directory -Force .aegis/d1-qualified | Out-Null
foreach ($repo in $selected) { Copy-Item ".aegis/data/$repo" ".aegis/d1-qualified/$repo" -Recurse -Force }
aegis dataset --data .aegis/d1-qualified --out eval/datasets/d1.parquet
```

Bu komut `d1.parquet` ile aynı sürümde `d1.json` manifestini üretir. Başka repo çıktıları `--data` köküne eklenirse `aegis dataset` onları da birleştirir; bu nedenle seçim kökü açıkça filtrelenmelidir.
