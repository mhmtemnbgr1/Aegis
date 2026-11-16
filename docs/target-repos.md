# Hedef Repolar

Gatekeeper eğitimi (D1), hafızalı tespit (D2) ve patch onarımı (D3) deneylerinde kullanılacak Python projeleri.

## Seçim Kriterleri

1. **BugsInPy'de yer alması:** Hatalı/düzeltilmiş sürümler ve başarısız testler hazır olduğundan D3 (patch doğrulama) aynı repolar üzerinde yapılabilir. Böylece D1–D3 aynı projeler üzerinde tutarlı olur.
2. **Zengin commit geçmişi:** SZZ ile yeterli sayıda bug-inducing commit çıkarılabilmeli.
3. **Hafif test ortamı:** Testler Docker sandbox'ta ağsız ve dakikalar içinde koşabilmeli. Ağır sayısal/GPU bağımlılığı olan projeler (pandas, keras, matplotlib, spaCy) bu yüzden dışarıda bırakıldı.
4. **Hâlâ aktif olması:** LLM eğitim verisi kirliliğine karşı, modellerin bilgi kesim tarihinden sonra yapılmış commit'lerden ayrı bir alt küme oluşturabilmek için.
5. **Alan çeşitliliği:** CLI, web framework, ağ, eşzamanlılık ve araç projeleri bir arada.

## Seçilen Repolar

| # | Repo | Alan | Neden |
| --- | --- | --- | --- |
| 1 | [psf/black](https://github.com/psf/black) | Kod biçimlendirici | Saf Python, kapsamlı ve hızlı test takımı, düzenli fix commit'leri |
| 2 | [spotify/luigi](https://github.com/spotify/luigi) | İş akışı orkestrasyonu | Tam geçmişte 595 bug-inducing commit; yeterli SZZ verisi |
| 3 | [sanic-org/sanic](https://github.com/sanic-org/sanic) | Web framework | BugsInPy kapsamındaki aktif proje; tam geçmişte 505 bug-inducing commit |
| 4 | [scrapy/scrapy](https://github.com/scrapy/scrapy) | Web tarama | Uzun geçmiş, eşzamanlılık (Twisted) hataları |
| 5 | [tornadoweb/tornado](https://github.com/tornadoweb/tornado) | Async ağ kütüphanesi | Race condition ve kaynak sızıntısı hataları; hafıza katkısını göstermek için ideal |
| 6 | [tqdm/tqdm](https://github.com/tqdm/tqdm) | İlerleme çubuğu | Küçük ve hızlı; pipeline'ı uçtan uca denemek için ilk pilot repo |

**Ölçülen ancak D1'e alınmayanlar:** [fastapi/fastapi](https://github.com/fastapi/fastapi) (138), [httpie/cli](https://github.com/httpie/cli) (167), yedek [cookiecutter/cookiecutter](https://github.com/cookiecutter/cookiecutter) (156) ve [nvbn/thefuck](https://github.com/nvbn/thefuck) (149) bug-inducing commit üretti; 200 eşiğinin altında kaldılar. [psf/requests](https://github.com/psf/requests) 354 pozitif üretse de BugsInPy kapsamı dışında olduğu için seçim kriteri gereği dahil edilmedi. HTTPie/cli demo fork'u olarak kullanılmaya devam eder, D1 eğitim verisine girmez.

## Kullanım Planı

- **Pilot (Faz 1, ilk hafta):** `tqdm`. Madencilik, SZZ ve metrikler önce burada doğrulanır.
- **Repo içi değerlendirme:** Her repo kendi geçmişiyle, zaman sıralı bölünerek eğitilir ve test edilir.
- **Repolar arası değerlendirme:** Birini dışarıda bırak (leave-one-project-out). 5 repoda eğitilip 6.'da test edilir; soğuk başlangıç senaryosunu ölçer.
- **Demo:** `httpie/cli` fork'u üzerinde hazırlanmış PR'lar.

> D1 pilotu ve tam madencilik sonuçları `eval/datasets/d1-report.md` içinde kayıtlıdır. Bir repo 200 bug-inducing commit eşiğinin altına düşerse D1'den çıkarılır ve yerine yeterli verisi olan repo eklenir.
