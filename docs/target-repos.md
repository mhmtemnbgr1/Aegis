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
| 2 | [fastapi/fastapi](https://github.com/fastapi/fastapi) | Web framework | Çok aktif, pytest tabanlı, gerçek dünya API hataları |
| 3 | [httpie/cli](https://github.com/httpie/cli) | HTTP istemcisi (CLI) | Orta boy, anlaşılır kod tabanı; demo için uygun |
| 4 | [scrapy/scrapy](https://github.com/scrapy/scrapy) | Web tarama | Uzun geçmiş, eşzamanlılık (Twisted) hataları |
| 5 | [tornadoweb/tornado](https://github.com/tornadoweb/tornado) | Async ağ kütüphanesi | Race condition ve kaynak sızıntısı hataları; hafıza katkısını göstermek için ideal |
| 6 | [tqdm/tqdm](https://github.com/tqdm/tqdm) | İlerleme çubuğu | Küçük ve hızlı; pipeline'ı uçtan uca denemek için ilk pilot repo |

**Yedek:** [spotify/luigi](https://github.com/spotify/luigi), [cookiecutter/cookiecutter](https://github.com/cookiecutter/cookiecutter). Seçilenlerden biri yeterli SZZ verisi üretmezse kullanılacak.

## Kullanım Planı

- **Pilot (Faz 1, ilk hafta):** `tqdm`. Madencilik, SZZ ve metrikler önce burada doğrulanır.
- **Repo içi değerlendirme:** Her repo kendi geçmişiyle, zaman sıralı bölünerek eğitilir ve test edilir.
- **Repolar arası değerlendirme:** Birini dışarıda bırak (leave-one-project-out). 5 repoda eğitilip 6.'da test edilir; soğuk başlangıç senaryosunu ölçer.
- **Demo:** `httpie/cli` fork'u üzerinde hazırlanmış PR'lar.

> Seçim Faz 1 pilotundan sonra gözden geçirilir. Bir repo yeterli etiketli veri üretmezse (ör. < 200 bug-inducing commit) yedeklerden biriyle değiştirilir ve bu dosya güncellenir.
