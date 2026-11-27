# Aegis — Proje Özeti ve Değerlendirme

Bu dosya projenin konumlandırmasını, katkılarını, araştırma sorularını, değerlendirme planını, demosunu ve sık sorulan soruları toplar. Teknik ayrıntılar için [architecture.md](architecture.md) dosyasına bakın.

## İçindekiler

1. [Ana Mesaj](#1-ana-mesaj)
2. [Mevcut Çözümler ve Boşluk](#2-mevcut-çözümler-ve-boşluk)
3. [Katkılar](#3-katkılar)
4. [Araştırma Soruları ve Başarı Kriterleri](#4-araştırma-soruları-ve-başarı-kriterleri)
5. [Değerlendirme Planı](#5-değerlendirme-planı)
6. [Geçerlilik Tehditleri](#6-geçerlilik-tehditleri)
7. [Demo Senaryosu](#7-demo-senaryosu)
8. [Sık Sorulan Sorular](#8-sık-sorulan-sorular)
9. [Ek Katkılar: Veri Seti ve Bildiri (opsiyonel)](#9-ek-katkılar-veri-seti-ve-bildiri-opsiyonel)
10. [Kaynakça](#10-kaynakça)

---

## 1. Ana Mesaj

> "Tekerleği yeniden icat etmiyoruz. Endüstrideki iki kopukluğu, yani maliyet-körü LLM botlarını ve aksiyonsuz akademik tahmin modellerini, hibrit bir mimaride birleştiriyoruz."

Tek cümlelik özet: **Aegis, riskli PR'ları ucuz bir ML modeliyle seçer, yerel bir LLM'e reponun geçmiş hatalarını hatırlatır ve doğrulanmış bulguları PR'a yorum olarak yazar.**

Hem yazılım madenciliği (MSR) literatürüne sadık kalan hem de güncel LLM ve RAG mühendisliğini gerçek bir problem üzerinde, tamamen yerel çalışarak uygulayan bir çalışma.

---

## 2. Mevcut Çözümler ve Boşluk

| Yaklaşım | Örnekler | Ne yapıyor? | Eksik kalan |
| --- | --- | --- | --- |
| LLM PR botları | PR-Agent (Qodo), CodeRabbit, GitHub Copilot code review | Diff'i LLM'e gönderip özet ve bulgu üretiyor | Repo geçmişi hafızası yok; her PR'a LLM çağırıyor; kodu bulut servisine gönderiyor |
| JIT hata tahmini (MSR) | Kamei vd. 2013, DeepJIT, CC2Vec, JITLine | Commit'in hatalı olma olasılığını tahmin ediyor | Hatanın ne olduğunu söylemiyor, düzeltme önermiyor, iş akışına girmiyor |
| Statik analiz | Semgrep, CodeQL, Ruff | Bilinen kalıpları deterministik olarak yakalıyor | İş mantığı hatalarını ve repoya özgü geçmişi göremiyor |
| Otomatik program onarımı (APR) | LLM tabanlı APR, BugsInPy/Defects4J benchmark'ları | Yeri bilinen bir hata için patch üretiyor | Hatanın nerede olduğunu önceden bilmeyi varsayıyor; PR akışına bağlı değil |

**Konumlandırma:** JIT tahminini **kapı**, bug-fix geçmişini **bağlam** olarak kullanan ve ikisini PR iş akışında, yerel bir LLM ile birleştiren açık kaynak bir araç. APR'yi **aksiyon** olarak eklemek (otomatik düzeltme) bu sürümün kapsamı dışındadır ve gelecek çalışmadır.

> Bu tablo güncel literatürle doğrulanmalı.

---

## 3. Katkılar

**K1 — Gatekeeper ile maliyet optimizasyonu.**
Klasik bir ML modeli, PR'ları LLM'e gitmeden önce eler. Böylece maliyet/performans dengesi ölçülebilir ve ayarlanabilir hale gelir. Maliyet, tasarımın ilk sınıf bir parçasıdır.

**K2 — Repo'ya özgü bug-fix hafızası.**
Genel LLM'ler reponun yazılı olmayan kurallarını ve geçmiş hatalarını bilmez. Fix commit'leri, SZZ eşlemeleri ve issue'lar hata kartları olarak saklanır. LLM'e "bu fonksiyon 4 ay önce değiştiğinde #89 numaralı sızıntı oluştu, şöyle çözülmüştü" bağlamı verilir.

**Kapsam dışı — K3: Tahminden aksiyona (gelecek çalışma).**
Düzeltme ve test ajanları ile Docker sandbox'ında çalışan bir doğrulayıcının, testle doğrulanmış suggestion blokları üretmesi planlanmıştı. Aralık 2026 teslimine sığmadığı ve ayrı bir araştırma problemi (APR) olduğu için v1'den çıkarıldı (Ekim 2026 kapsam revizyonu). Mimari buna hazırdır: bulgular zaten dosya, satır ve kanıtla doğrulanmış olarak üretilir.

**Projenin katkıları K1 ve K2'dir.** Takvim ve kesme çizgileri: [TODO.md](../TODO.md).

---

## 4. Araştırma Soruları ve Başarı Kriterleri

| ID | Soru |
| --- | --- |
| **RQ1** | Gatekeeper LLM çağrılarını ve maliyeti ne kadar azaltır; bu sırada hatalı değişikliklerin ne kadarı kaçırılır? Ucuz bir LLM'in triage yapmasından daha mı iyidir? |
| **RQ2** | Bug-fix hafızası tespit doğruluğunu hafızasız incelemeye göre artırır mı? Bu iyileşme hafızanın **içeriğinden** mi, yoksa yalnızca daha uzun bağlamdan mı gelir? |
| ~~RQ3~~ | *Kapsam dışı (patch üretimi; gelecek çalışma). Numaralandırma issue'larla uyum için korunur.* |
| **RQ4** *(opsiyonel)* | Aegis, aynı yerel LLM'i kullanan mevcut bir PR botuna (PR-Agent) göre maliyet ve doğruluk açısından nerede durur? |
| **RQ5** *(opsiyonel)* | Geliştiriciler Aegis'in yorumlarını PR-Agent'ın yorumlarına göre daha doğru ve faydalı buluyor mu? |

**Gatekeeper sonucu nasıl sunulacak:** Tek bir "≥ %X recall" vaadi yerine **maliyet–recall eğrisinin tamamı** raporlanır ve üzerinde iki işletme noktası vurgulanır:

- **Maliyet odaklı nokta:** PR'ların ~%60'ı elenir. Bu noktada hataların ne kadarının yakalandığı raporlanır.
- **Güvenlik odaklı nokta:** Hataların ≥ %90'ı yakalanır. Bu noktada PR'ların ne kadarının elendiği raporlanır.

Böylece model ne kadar iyi çıkarsa çıksın sonuç savunulabilir olur; ekip seçimini bir dengeye göre yapar. Kıyas noktası, aynı eğri üzerinde sezgisel kural ve ucuz LLM triage'dır.

**Diğer hedefler (ilk veri gelince gözden geçirilecek):**

| Metrik | Hedef |
| --- | --- |
| Gatekeeper ROC-AUC | Sezgisel kuraldan ve ucuz LLM triage'dan anlamlı derecede yüksek |
| Hafızalı analizde F1 iyileşmesi | Hafızasız ve plasebo varyantlarından istatistiksel olarak anlamlı derecede iyi |
| PR başına ortalama LLM yükü (çağrı, token, süre) | "Her PR'a LLM" taban çizgisine göre maliyet odaklı işletme noktasında ≥ %50 azalma |
| PR başına uçtan uca süre (p95) | ≤ 5 dk |
| Kullanıcı çalışması (RQ5, opsiyonel) | Faydalılık puanında PR-Agent'tan anlamlı derecede yüksek |

---

## 5. Değerlendirme Planı

### 5.1 Veri Setleri

| ID | Veri seti | Kaynak | Hedef boyut | RQ |
| --- | --- | --- | --- | --- |
| D1 | SZZ ile etiketlenmiş commit ve PR'lar | 6 hedef repo ([target-repos.md](target-repos.md)), tüm geçmiş | Tüm commit'ler (repo başına ≥ 200 pozitif) | RQ1 |
| D2 | Tersine çevrilmiş gerçek düzeltmeler (düzeltmenin sildiği satırlar = beklenen bulgu) ve temiz commit'ler | D1 repolarından tabakalı örnekleme | 300 hatalı + 300 temiz; yeni set için 102 örneklik insan incelemesi hazırlanıyor | RQ2, RQ4, RQ5 |
| D4 | Demo ve dogfooding PR'ları | Ekip | ≥ 30 PR | Maliyet, süre |

> SZZ satırları gürültülü olduğu için (elle kontrolde %19–31 doğru) D2'nin varsayılan hatalı örnekleri gerçek düzeltmelerin tersine çevrilmesiyle kurulur: hatalı satırların yeri kesin bilinir. Eski SZZ örneklerinden 102'si iki bağımsız etiket setiyle kontrol edildi; ortak etiketler yalnızca SZZ gerçekçilik setinde raporlanır. Revert seti için ayrı bir 102 örnekli insan değerlendirmesi hazırlanır. Eşleştirilmiş McNemar testinde birkaç yüz örnek, orta büyüklükteki farkları yakalamak için yeterlidir.

### 5.1.1 Kullanıcı Çalışması (RQ5, opsiyonel)

- **Katılımcılar:** 6–10 geliştirici (bölüm öğrencileri, stajyerler, mezunlar).
- **Malzeme:** D2'den 20 PR. Her PR için Aegis ve PR-Agent yorumları **kaynağı gizlenerek** ve rastgele sırayla gösterilir.
- **Ölçek:** Her yorum için 1–5 Likert: doğru mu, faydalı mı, uygular mısın?
- **Analiz:** Wilcoxon işaretli sıra testi.
- **Araç:** Basit bir form (Google Forms veya benzeri). Etik açısından kişisel veri toplanmaz.

### 5.2 Taban Çizgileri ve Ablation Matrisi

| Boyut | Varyantlar |
| --- | --- |
| Gatekeeper | yok (her PR'a LLM) · sezgisel kural · **ucuz LLM ile triage** · LR · RF · LightGBM |
| Hafıza | yok · **plasebo** (aynı uzunlukta rastgele kartlar) · yalnızca vektör · yalnızca yapısal · hibrit |
| Rakip araç *(opsiyonel)* | **PR-Agent** (aynı yerel LLM, aynı D2) |
| LLM | Ollama üzerinde 2 yerel açık kod modeli (ör. Qwen2.5-Coder 7B ve daha büyük bir sürüm); bulut modeli yok |

- **Ucuz LLM triage:** Akla gelecek "neden XGBoost?" sorusunun cevabıdır. Maliyet, recall ve açıklanabilirlik birlikte karşılaştırılır.
- **Plasebo hafıza:** İyileşmenin prompt uzunluğundan değil, hafızanın içeriğinden geldiğini kanıtlar.
- **PR-Agent:** "CodeRabbit'ten ne farkınız var?" sorusunun sayısal cevabıdır. Açık kaynak olduğu ve Ollama'yı desteklediği için aynı yerel model ve veriyle koşturulabilir.

**RQ1 ucuz LLM triage sonucu (#67):** Qwen2.5-Coder 1.5B, aynı D1 test kümesindeki 1.250 PR'da LR ve sezgisel taban çizgileriyle karşılaştırıldı. Hücreler 25 zaman penceresindeki yakalanan hatalı PR oranının ortalaması ve %95 bootstrap güven aralığıdır. Efor payı, LLM'e gönderilen PR oranını gösterir.

| LLM'e gönderilen PR | Ucuz LLM triage | LR (tam + hafıza) | Sezgisel |
| ---: | ---: | ---: | ---: |
| %10 | %9,2 [5,3; 13,5] | %37,5 [28,8; 47,5] | %24,8 [17,4; 34,2] |
| %20 | %23,0 [15,7; 30,4] | %63,0 [55,4; 71,1] | %49,1 [40,6; 58,3] |
| %40 | %53,3 [44,0; 62,1] | %84,9 [78,8; 90,6] | %74,1 [65,4; 81,3] |
| %60 | %84,0 [76,6; 90,9] | %94,4 [90,7; 97,7] | %92,4 [88,3; 96,2] |

LLM triage PR başına ortalama 0,8 sn, 1.308 girdi ve 61 çıktı tokenı kullandı. Eşleştirilmiş Wilcoxon testi, LLM'in her efor payında LR'dan anlamlı ölçüde düşük recall verdiğini (p ≤ 0,018), sezgisel taban çizgisinden de anlamlı ölçüde düşük olduğunu (p ≤ 0,003) gösterdi. [Ham sonuçlar ve ayrıntılı analiz](../eval/results/rq1-triage/qwen2.5-coder_1.5b/summary.md).

### 5.3 Metrikler

| RQ | Metrikler |
| --- | --- |
| RQ1 | ROC-AUC, PR-AUC, F1, MCC, Recall@%20 efor, P<sub>opt</sub>; **LLM'e gönderilen PR oranı – yakalanan hatalı PR oranı eğrisi**; triage başına token ve süre |
| RQ2 | Satır düzeyinde precision/recall/F1, temiz commit'lerde yanlış alarm oranı, getirme Recall@k ve MRR |
| RQ4 | Aynı D2 alt kümesinde F1, PR başına LLM çağrısı, token ve süre |
| RQ5 | Doğruluk, faydalılık ve uygulanabilirlik Likert puanları |

**İstatistik:** Wilcoxon ve McNemar testleri; birden fazla seed.

---

## 6. Geçerlilik Tehditleri

| Tehdit | Önlem |
| --- | --- |
| SZZ etiketleri gürültülü | MA-SZZ filtreleri, 200 örneklik elle doğrulama, elle etiketli alt küme |
| Zamansal sızıntı (geleceği görme) | Zaman sıralı bölme, etiket gecikmesi tamponu, hafızada zamansal filtre |
| LLM eğitim verisi kirliliği (popüler hataların düzeltmeleri ezberlenmiş olabilir) | Model bilgi kesim tarihinden sonraki commit'lerden ayrı alt küme |
| Az sayıda repo (dış geçerlilik) | Farklı alanlardan 6 repo, leave-one-project-out |
| Küçük yerel model (7B) zayıf bulgular üretebilir | RQ2 mutlak kaliteyi değil hafızanın getirdiği iyileşmeyi ölçer; ikinci, daha büyük bir yerel modelle tekrarlanır |
| Elle etiketlemede öznellik | İki kişi bağımsız etiketler; Cohen's κ raporlanır |
| PR etiketinin commit etiketinden türetilmesi | Tanım açıkça yazılır (en az bir bug-inducing commit); squash-merge yapan ve yapmayan repolar ayrı raporlanır |
| Özelliklerde zamansal sızıntı | Zorunlu `as_of` parametresi ve bunu doğrulayan birim testi |
| Kullanıcı çalışmasının küçük örneklemi (yapılırsa) | Sonuçlar keşif amaçlı sunulur; kör ve rastgele sıralı tasarım |

---

## 7. Demo Senaryosu

Yaklaşık 5 dakika; [muratEfeErgin/cli fork'undaki](https://github.com/muratEfeErgin/cli) açık demo PR'larıyla:

1. **Düşük risk — [PR #2](https://github.com/muratEfeErgin/cli/pull/2):** Gerçek D1'den eğitilen LR modeliyle demo eşiğinde skor `0.014` çıktı; LLM çağrılmadı ve bulgu üretilmedi.
2. **Yüksek risk — [`Retry-After` PR #3](https://github.com/muratEfeErgin/cli/pull/3):** Demo eşiğinde skor `0.215`; Qwen geçerli JSON üretti, üç gerçek hafıza kartı kullandı ve diff'te olmayan iki öneriyi eledi.
3. **Orta risk/geçmiş hata — [PR #4](https://github.com/muratEfeErgin/cli/pull/4):** Skor `0.055`; Qwen `LogLevel` enum'u yerine string kullanılmasını buldu, iki satıra bulgu yazdı ve gerçek geçmişten `BC-44d3cff03f` kartını getirdi.
4. **Orta risk/prompt injection — [PR #5](https://github.com/muratEfeErgin/cli/pull/5):** Skor `0.126`; Qwen `subprocess.call(..., shell=True)` kullanımını güvensiz buldu. Deterministik injection denetimi de `httpie/hooks.py:5` satırını ayrıca işaretledi.
5. **Maliyet karşılaştırması:** "Her PR'a LLM" ile Aegis arasındaki LLM çağrısı, token ve süre farkı [RQ1/RQ2 sonuç grafiği](results.md) üzerinden gösterilir.

Demo PR'ları [public HTTPie fork'unda](https://github.com/muratEfeErgin/cli) açık ve dört dal da yalnızca kendi senaryo değişikliğini içeriyor. Yerel prova gerçek HTTPie geçmişinden 120 hata kartını ve gerçek D1 veri kümesinden eğitilmiş LR modelini kullandı (ROC AUC `0.832`); sentetik veri kullanılmadı. Dört PR da yerel Ollama ile en az iki kez çalıştırıldı. Demo için `[gatekeeper]` eşikleri `low = 0.05`, `high = 0.15` olarak ayarlandı; bunlar yalnızca sunum eşiğidir. Qwen şema düzeltmesi ve prompt-injection talimatı PR #99'da hazır. Gerçek geçmiş/model paketi fork'un `aegis-state` Release'inde yayımlandı. Aegis deposu private olduğundan [kurulum PR'ı #1](https://github.com/muratEfeErgin/cli/pull/1), private Action'ı okumak için `AEGIS_ACTION_READ_TOKEN` repo secret'ını bekliyor; yönetici bu secret'ı ekleyip PR'ı birleştirmeden GitHub Action check'i çalışamaz. Yerel CLI demosu doğrulandı; otomatik GitHub check'i henüz doğrulanmadı.

**Hazırlık gereklilikleri:**
- [ ] Demo PR'ları hazır ve en az 2 kez prova edilmiş
- [ ] Ollama ile çevrimdışı yedek çalışıyor
- [ ] Kayıtlı yedek video (donanım veya Ollama sorununa karşı)
- [ ] Tek sayfalık sonuç grafiği (RQ1 eğrisi + RQ2 sonucu)

---

## 8. Sık Sorulan Sorular

### "CodeRabbit veya Copilot code review zaten var. Farkınız ne?"
Üç fark var: Her PR'a LLM çağırmıyoruz (K1); LLM'e reponun kendi geçmiş hatalarını veriyoruz (K2); her şey yerelde çalışıyor, kod dışarı çıkmıyor ve API ücreti yok. K1 ve K2'nin etkisini ablation deneyleriyle (RQ1, RQ2) sayıyla gösteriyoruz.

### "Neden XGBoost/LightGBM? Küçük bir LLM de PR'ın riskli olup olmadığına karar veremez mi?"
Bunu ölçtük (RQ1, #67): RQ1 eğrisinin 25 zaman penceresinden alınan 1.250 PR'a yerel Qwen2.5-Coder 1.5B ile risk puanı verildi ve aynı PR'lardaki LR ve sezgisel taban çizgileriyle karşılaştırıldı. PR'ların %40'ı incelemeye ayrıldığında LLM triage hatalı PR'ların %53,3'ünü; LR %84,9'unu, sezgisel kural %74,1'ini yakaladı. LLM triage PR başına ortalama 0,8 sn ve 1.369 toplam token kullandı; LR puanlaması CPU'da milisaniyeler sürer. Ayrıntılar ve diğer efor payları §5.2'deki tabloda.

### "Hafızalı versiyonun iyi çıkması sadece prompt uzadığı için olamaz mı?"
Bunu iki yerde plaseboyla sınıyoruz. LLM'siz ölçümde hafıza sinyali risk modeline eklenince dar bütçede (%10 LLM payı) yakalanan hatalı PR oranı 4 puan artıyor (p = 0,012); aynı dağılımda ama bilgisiz plasebo hiçbir kazanç getirmiyor. LLM'li RQ2'de (#36) hafızalı inceleme, aynı sayıda ilgisiz kart (aynı repodan, commit'in dosyalarına dokunmayan) verilen plasebo varyantıyla karşılaştırılıyor; bu deney koşturulmayı bekliyor.

### "JIT defect prediction zaten var. Yeni olan ne?"
Bu modeller tek başına bir olasılık üretip bırakıyor. Biz bu olasılığı LLM için bir maliyet kapısı olarak, SZZ eşlemelerini de LLM'e bağlam olarak kullanıyoruz. Tahmin, açıklamalı ve somut bir inceleme yorumuna dönüşüyor.

### "SZZ etiketleri gürültülü değil mi?"
Evet, ve bunu ölçtük. Elle kontrol edilen 50 eşlemenin %31'i doğru [%95 GA: 19–44]; fix tespitinin kesinliği ise kurallarla %71'den %86'ya çıktı. Literatürdeki üç standart iyileştirmeyi denedik (hata etiketli issue şartı, taşınan satırları izleme, tarih kontrolü): doğruluğu artırmadılar ya da veriyi yok ettiler (issue şartıyla tornado'da hiç hatalı commit kalmıyor). Bu yüzden: (1) sonuçları ölçülmüş bir sınırlama olarak raporluyoruz; (2) gürültü sonuçları bizim aleyhimize çalışır, buna rağmen model sezgisel kuraldan anlamlı derecede iyi; (3) RQ2'nin hatalı örneklerinde SZZ'yi hiç kullanmıyoruz: gerçek düzeltmeleri tersine çeviriyoruz, böylece hatalı satırların yeri kesin biliniyor (etiket doğruluğu fix tespitine bağlı, %96). Temiz örnekler iki etiket setiyle kontrol edildi (#69).

### "Gatekeeper hatalı bir PR'ı geçirirse?"
Eşik bütçe–recall eğrisinden bilinçli olarak seçiliyor. Maliyet odaklı noktada PR'ların %58'i elenirken hatalı PR'ların %82'si yine yakalanıyor; güvenlik odaklı noktada hedef %90 recall'ı tutturamadık (%83), çünkü eşik bir önceki pencereden seçiliyor ve dağılım kayıyor. Düşük bantta da risk skoru yorum olarak yazılıyor ve `aegis:force` etiketiyle tam inceleme zorlanabiliyor. Aegis insan incelemesinin yerini almıyor, önceliklendiriyor.

### "Veri sızıntısı var mı?"
Hayır. Doğrulama zaman sıralı, hafıza zamansal filtreli ve etiketi henüz oluşmamış son aylar eğitime alınmıyor.

### "LLM bu repoların hatalarını ezberlemiş olamaz mı?"
Olabilir; iki önlemimiz var. (1) RQ2 mutlak başarıyı değil hafızanın getirdiği farkı ölçüyor: ezber varsa hafızasız, plasebo ve hafızalı varyantların hepsine aynı ölçüde yarar, fark değişmez. (2) Model bilgi kesiminden (2024-09) sonraki commit'ler ayrı alt kümede raporlanıyor. D2'de bu kapsamda yalnızca 17 commit var; bu yüzden o tablo keşif amaçlı.

### "Kötü niyetli bir PR, LLM'i kandırıp bulguları gizletebilir mi?"
PR içeriği prompt'ta veri olarak işaretleniyor ve ajanın hiçbir araç yetkisi yok. Çıktı şeması fazladan alan kabul etmiyor; uydurma kanıtlı bulgular düşüyor. Bilinen saldırı kalıpları da modelden bağımsız, deterministik bir dedektörle güvenlik bulgusu olarak raporlanıyor; model kandırılsa bile bu bulgu bastırılamıyor. 14 saldırı örneğiyle regresyon testlerimiz var; demoda canlı gösteriyoruz.

### "PR kodunu CI'da çalıştırmak güvenli mi?"
Aegis PR kodunu çalıştırmıyor, yalnızca diff'i okuyor. `pull_request_target` kullanmıyoruz ve yapılandırma taban daldan okunuyor; bir PR kendi incelemesini gevşetemiyor.

### "İlk kurulum ne kadar sürüyor? Her PR'da tüm geçmiş mi taranıyor?"
Hayır. İlk madencilik ve indeksleme yerelde bir kez yapılıyor ve GitHub Release asset'i olarak yükleniyor. Action bu arşivi indiriyor; her PR'da geçmiş yeniden taranmıyor. Tüm geçmiş üzerinde SZZ, en büyük hedef repoda (scrapy) 4 dakikadan kısa sürüyor. `main`'e her merge'de yalnızca yeni commit'ler işleniyor (tqdm'de tam tarama 2 dk 48 sn, yeni commit yokken 3 sn).

### "Neden otomatik düzeltme (patch) üretmiyorsunuz?"
Bilinçli bir kapsam kararı. Testle doğrulanmış patch üretimi ayrı bir araştırma problemi (APR) ve güvenilir yapılması için sandbox ile büyük bir benchmark gerekiyor. v1'de katkıyı ölçülebilir iki parçaya (K1, K2) yoğunlaştırdık; patch hattı gelecek çalışma. Mimari buna hazır: bulgular zaten satır ve kanıtla doğrulanmış biçimde üretiliyor.

### "Kullanıcılar bu yorumları gerçekten faydalı buluyor mu?"
Bunu ölçmek için 6–10 geliştiriciyle kör bir kullanıcı çalışması tasarladık (RQ5, isteğe bağlı): Aegis ve PR-Agent yorumları kaynak gizlenerek puanlatılıyor. Zaman kalırsa yapılacak; yapılmazsa gelecek çalışma olarak kalacak.

### "Geçmişi olmayan yeni bir repoda ne olacak?"
Repolar arası genel model kullanılıyor: yalnızca diğer 5 repoyla eğitilen model, repo içi modelle aynı başarıda (ROC-AUC 0,805'e karşı 0,797). Hafıza boşsa analiz hafızasız yapılıyor.

### "Kodumuz dışarı mı gidiyor?"
Hayır. Aegis yalnızca yerel modelle (Ollama) ve yerel embedding ile çalışıyor; kod makineden veya runner'dan dışarı çıkmıyor, API anahtarı da gerekmiyor.

### "Neden LangGraph gibi hazır bir ajan çerçevesi kullanmadınız?"
Zincir kısa ve sabit. Kendi durum makinemiz bağımlılığı azaltıyor ve her adımı test edilebilir kılıyor.

### "API çökerse PR kilitlenir mi?"
Hayır. Fail-open prensibi var: check `neutral` sonuçlanıyor ve bir uyarı yorumu bırakılıyor.

### "Maliyeti ne kadar?"
API ücreti yok: tüm modeller yerelde (Ollama ve yerel embedding) çalışıyor. Maliyet; LLM'e giden PR oranı, token sayısı ve GPU/CPU süresi olarak ölçülüyor. Gatekeeper sayesinde düşük riskli PR'larda LLM hiç çalışmıyor.

---

## 9. Ek Katkılar: Veri Seti ve Bildiri (opsiyonel)

- **Açık veri seti:** SZZ ile etiketlenmiş Python JIT veri seti (D1/D2) ve hata kartları açık lisansla yayınlanır. Python için bu tür veri setleri az bulunuyor.
- **Bildiri:** Sonuçlar UYMS (Ulusal Yazılım Mühendisliği Sempozyumu) veya benzeri bir konferansa gönderilir.

---

## 10. Kaynakça

> Künyeler Kasım 2026'da yayıncı sayfaları ve dizinlerle doğrulandı. Parantez içi: projede nerede kullanıldığı.

**Hata getiren değişiklikler ve JIT hata tahmini**

- J. Śliwerski, T. Zimmermann, A. Zeller. *When do changes induce fixes?* Proc. 2nd Int. Workshop on Mining Software Repositories (MSR 2005), s. 24–28. (SZZ'nin temeli; `aegis.mining.szz`)
- D. A. da Costa, S. McIntosh, W. Shang, U. Kulesza, R. Coelho, A. E. Hassan. *A Framework for Evaluating the Results of the SZZ Approach for Identifying Bug-Introducing Changes.* IEEE TSE 43(7):641–657, 2017. doi:10.1109/TSE.2016.2616306 (MA-SZZ varyantı)
- Y. Kamei, E. Shihab, B. Adams, A. E. Hassan, A. Mockus, A. Sinha, N. Ubayashi. *A Large-Scale Empirical Study of Just-in-Time Quality Assurance.* IEEE TSE 39(6):757–773, 2013. doi:10.1109/TSE.2012.70 (14 Kamei metriği, K1)
- T. Hoang, H. K. Dam, Y. Kamei, D. Lo, N. Ubayashi. *DeepJIT: An End-to-End Deep Learning Framework for Just-in-Time Defect Prediction.* MSR 2019, s. 34–45. doi:10.1109/MSR.2019.00016 (ilgili çalışma)
- C. Pornprasit, C. Tantithamthavorn. *JITLine: A Simpler, Better, Faster, Finer-grained Just-In-Time Defect Prediction.* MSR 2021, s. 369–379. doi:10.1109/MSR52588.2021.00049 (ilgili çalışma; basit modellerin derin modellerle yarışabildiği)

**Veri ve araçlar**

- D. Spadini, M. Aniche, A. Bacchelli. *PyDriller: Python Framework for Mining Software Repositories.* ESEC/FSE 2018, s. 908–911. doi:10.1145/3236024.3264598 (madencilik)
- R. Widyasari vd. *BugsInPy: A Database of Existing Bugs in Python Programs to Enable Controlled Testing and Debugging Studies.* ESEC/FSE 2020, s. 1556–1560. doi:10.1145/3368089.3417943 (D1 repo seçim kriteri)
- B. Hui vd. *Qwen2.5-Coder Technical Report.* arXiv:2409.12186, 2024. (yerel LLM)

**Modeller, kalibrasyon ve açıklama**

- F. Pedregosa vd. *Scikit-learn: Machine Learning in Python.* JMLR 12:2825–2830, 2011. (LR, RF)
- G. Ke vd. *LightGBM: A Highly Efficient Gradient Boosting Decision Tree.* NeurIPS 2017 (NIPS 30), s. 3146–3154. (LightGBM)
- J. C. Platt. *Probabilistic Outputs for Support Vector Machines and Comparisons to Regularized Likelihood Methods.* Advances in Large Margin Classifiers, MIT Press, 1999. (sigmoid kalibrasyon)
- S. M. Lundberg, S.-I. Lee. *A Unified Approach to Interpreting Model Predictions.* NeurIPS 2017 (NIPS 30), s. 4765–4774. (SHAP açıklamaları)

**Hafıza ve getirme**

- P. Lewis vd. *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks.* NeurIPS 2020 (NeurIPS 33). (K2'nin dayandığı fikir)
- S. Deerwester, S. T. Dumais, G. W. Furnas, T. K. Landauer, R. Harshman. *Indexing by Latent Semantic Analysis.* JASIS 41(6):391–407, 1990. (LSA vektör arama)
- S. Robertson, H. Zaragoza. *The Probabilistic Relevance Framework: BM25 and Beyond.* Foundations and Trends in Information Retrieval 3(4):333–389, 2009. doi:10.1561/1500000019 (BM25)
- G. V. Cormack, C. L. A. Clarke, S. Büttcher. *Reciprocal Rank Fusion Outperforms Condorcet and Individual Rank Learning Methods.* SIGIR 2009, s. 758–759. doi:10.1145/1571941.1572114 (hibrit arama, RRF)

**İstatistik**

- F. Wilcoxon. *Individual Comparisons by Ranking Methods.* Biometrics Bulletin 1(6):80–83, 1945. (eşleştirilmiş karşılaştırmalar)
- Q. McNemar. *Note on the Sampling Error of the Difference Between Correlated Proportions or Percentages.* Psychometrika 12(2):153–157, 1947. doi:10.1007/BF02295996 (RQ2 eşleştirilmiş ikili sonuçlar)
- J. Cohen. *A Coefficient of Agreement for Nominal Scales.* Educational and Psychological Measurement 20(1):37–46, 1960. doi:10.1177/001316446002000104 (etiket uyumu, κ)
- S. Holm. *A Simple Sequentially Rejective Multiple Test Procedure.* Scandinavian Journal of Statistics 6(2):65–70, 1979. (çoklu karşılaştırma düzeltmesi)
