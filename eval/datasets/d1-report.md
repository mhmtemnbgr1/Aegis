# D1 veri seti madencilik raporu

**Üretim tarihi:** 2026-11-16 19:18 UTC  
**Aegis:** `0.0.1` · **Şema:** `1` · **SZZ:** MA-SZZ  
**Eşik:** repo başına en az 200 bug-inducing commit (`aegis dataset --min-positives`, varsayılan 200)

D1, BugsInPy'de bulunan altı açık kaynak Python projesinin gerçek Git geçmişlerinden üretildi; sentetik ya da mock satır kullanılmadı. Taranan her repo'nun HEAD SHA'sı `d1.json` manifestinde kayıtlıdır. Parquet; commit SHA'sı ve tarihi, Kamei özellikleri, riskli yol ve test oranı, bug-fix hafızası özellikleri (`mem_func_bugs`, `mem_file_bugs`), SZZ tabanlı `buggy` etiketi ve etiketin bilindiği `fixed_at` zamanını içerir. Kaynak kod diff'leri ve commit mesajları veri setine alınmamıştır.

## Dahil edilen depolar

| Repo | Commit satırı | Fix | Bug-inducing | Pozitif oran | Kaynak lisansı |
| --- | ---: | ---: | ---: | ---: | --- |
| [psf/black](https://github.com/psf/black) | 2.502 | 541 | 386 | %15,4 | MIT |
| [sanic-org/sanic](https://github.com/sanic-org/sanic) | 2.112 | 390 | 505 | %23,9 | MIT |
| [scrapy/scrapy](https://github.com/scrapy/scrapy) | 9.625 | 1.140 | 1.139 | %11,8 | BSD-3-Clause |
| [spotify/luigi](https://github.com/spotify/luigi) | 3.047 | 543 | 595 | %19,5 | Apache-2.0 |
| [tornadoweb/tornado](https://github.com/tornadoweb/tornado) | 4.138 | 658 | 578 | %14,0 | Apache-2.0 |
| [tqdm/tqdm](https://github.com/tqdm/tqdm) | 1.821 | 400 | 396 | %21,8 | MPL-2.0 ve MIT |
| **Toplam** | **23.245** | **3.672** | **3.599** | **%15,5** | — |

Parquet `d1.parquet`, makinece okunabilir sürüm manifesti `d1.json` içindedir. Manifest her repo için HEAD SHA, SZZ çeşidi, etiket kesim tarihi, sayımlar ve D1'e alınıp alınmadığını (`included`) içerir. Parquet SHA-256: `841a93cb9e0ef1794d6f7cd259c892021692fa35c68c88abab2ef8555c237259`.

## Eşiğin altında kalan adaylar

| Repo | Bug-inducing | Karar |
| --- | ---: | --- |
| [fastapi/fastapi](https://github.com/fastapi/fastapi) | 138 | Luigi ile değiştirildi |
| [httpie/cli](https://github.com/httpie/cli) | 168 | Sanic ile değiştirildi; demo reposu olarak kaldı |
| [cookiecutter/cookiecutter](https://github.com/cookiecutter/cookiecutter) | 156 | Yedek denendi, eşik altı |
| [nvbn/thefuck](https://github.com/nvbn/thefuck) | 149 | BugsInPy adayı olarak denendi, eşik altı |

FastAPI ve HTTPie'nin madencilik çıktıları silinmez: `aegis dataset` onları manifestte `included: false` ile listeler ama D1'e almaz. HTTPie verisi demo fork'unun durum arşivi ve hafızası için kullanılmaya devam eder. `psf/requests` 354 pozitif üretse de BugsInPy kapsamına girmediği için seçim kriteri gereği eklenmedi.

## Yeniden üretme

```bash
aegis mine https://github.com/spotify/luigi
aegis mine https://github.com/sanic-org/sanic
aegis index .aegis/repos/spotify__luigi        # hafıza kartları; mem_* sütunları için dataset'ten önce
aegis index .aegis/repos/sanic-org__sanic
aegis dataset                                   # D1: eşik altındaki repolar otomatik dışarıda kalır
aegis dataset --level pr                        # PR düzeyinde D1
```

Diğer dört repo (black, scrapy, tornado, tqdm) için aynı `mine` ve `index` adımları geçerlidir. Bu dosyadaki sayılar `.aegis/data` altındaki çıktılardan üretildi; black, scrapy ve tornado'nun HEAD'i 13 Kasım klonlarıdır, bu yüzden #95'teki ilk rapordan birkaç commit farklıdır.
