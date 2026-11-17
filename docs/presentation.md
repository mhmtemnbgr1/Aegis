# Aegis — Sunum ve Tez Gereklilikleri

Bu dosya jüri sunumu ve tez için gereken her şeyi toplar: konumlandırma, katkılar, araştırma soruları, değerlendirme planı, demo ve olası sorular. Teknik ayrıntılar için [architecture.md](architecture.md) dosyasına bakın.

## İçindekiler

1. [Ana Mesaj](#1-ana-mesaj)
2. [Mevcut Çözümler ve Boşluk](#2-mevcut-çözümler-ve-boşluk)
3. [Katkılar](#3-katkılar)
4. [Araştırma Soruları ve Başarı Kriterleri](#4-araştırma-soruları-ve-başarı-kriterleri)
5. [Değerlendirme Planı](#5-değerlendirme-planı)
6. [Geçerlilik Tehditleri](#6-geçerlilik-tehditleri)
7. [Demo Senaryosu](#7-demo-senaryosu)
8. [Olası Jüri Soruları](#8-olası-jüri-soruları)
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

> Bu tablo tez yazımında güncel literatür taramasıyla doğrulanmalı.

---

## 3. Katkılar

**K1 — Gatekeeper ile maliyet optimizasyonu.**
Klasik bir ML modeli, PR'ları LLM'e gitmeden önce eler. Böylece maliyet/performans dengesi ölçülebilir ve ayarlanabilir hale gelir. Jüriye maliyet mühendisliği düşündüğümüzü gösterir.

**K2 — Repo'ya özgü bug-fix hafızası.**
Genel LLM'ler reponun yazılı olmayan kurallarını ve geçmiş hatalarını bilmez. Fix commit'leri, SZZ eşlemeleri ve issue'lar hata kartları olarak saklanır. LLM'e "bu fonksiyon 4 ay önce değiştiğinde #89 numaralı sızıntı oluştu, şöyle çözülmüştü" bağlamı verilir.

**Kapsam dışı — K3: Tahminden aksiyona (gelecek çalışma).**
Düzeltme ve test ajanları ile Docker sandbox'ında çalışan bir doğrulayıcının, testle doğrulanmış suggestion blokları üretmesi planlanmıştı. Aralık 2026 teslimine sığmadığı ve ayrı bir araştırma problemi (APR) olduğu için v1'den çıkarıldı (Ekim 2026 kapsam revizyonu). Mimari buna hazırdır: bulgular zaten dosya, satır ve kanıtla doğrulanmış olarak üretilir.

**Tezin katkıları K1 ve K2'dir.** Takvim ve kesme çizgileri: [TODO.md](../TODO.md).

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
| D2 | Bug-inducing commit'ler (sonradan düzeltilen satırlar = beklenen bulgu) ve temiz commit'ler | D1'den tabakalı örnekleme | ~300 hatalı + ~300 temiz; ~100'ü elle etiketli | RQ2, RQ4, RQ5 |
| D4 | Demo ve dogfooding PR'ları | Ekip | ≥ 30 PR | Maliyet, süre |

> D2'de SZZ satırları gürültülü olabilir. Bu yüzden ~100 örnek iki kişi tarafından elle etiketlenir ve sonuçlar hem otomatik hem elle etiketli alt küme için raporlanır. Eşleştirilmiş McNemar testinde birkaç yüz örnek, orta büyüklükteki farkları yakalamak için yeterlidir.

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

1. **Düşük risk — [PR #2](https://github.com/muratEfeErgin/cli/pull/2):** Gerçek D1'den eğitilen LR modeliyle skor `0.014` çıktı; LLM çağrılmadı ve bulgu üretilmedi.
2. **`Retry-After` değişikliği — [PR #3](https://github.com/muratEfeErgin/cli/pull/3):** Varsayılan eşikle skor `0.215` ve düşük risk çıktı; Ollama atlandı. Yalnızca yerel prova için `low_threshold = 0.05` kullanıldığında orta risk/LLM yolu çalıştı, ancak Qwen yanıtındaki `confidence > 1` şema doğrulamasını geçemedi. Bu sonuç LLM gösterimi için henüz hazır değil.
3. **Geçmiş hata — [PR #4](https://github.com/muratEfeErgin/cli/pull/4):** Varsayılan eşikle `0.055` düşük risk; yerel prova eşiğiyle orta risk oldu. Qwen, `LogLevel` enum'u yerine string kullanılmasını buldu ve gerçek geçmişten `BC-44d3cff03f` kartını getirdi.
4. **Prompt injection — [PR #5](https://github.com/muratEfeErgin/cli/pull/5):** Varsayılan eşikle `0.126` düşük risk; deterministik denetim `httpie/hooks.py:5` satırında yüksek önem dereceli injection bulgusu verdi. Yerel prova eşiğiyle Ollama çağrıldı ve bulgu sonuçta kaldı; model özeti injection metnini talimat olarak anladığı için bu tek başına modelin injection'a direndiğini kanıtlamaz.
5. **Maliyet karşılaştırması:** "Her PR'a LLM" ile Aegis arasındaki LLM çağrısı, token ve süre farkı [RQ1/RQ2 sonuç grafiği](results.md) üzerinden gösterilir.

Demo PR'ları [public HTTPie fork'unda](https://github.com/muratEfeErgin/cli) açık. Aegis Action'ı private olduğu için public fork'taki GitHub Actions onu yükleyemiyor; [kurulum PR'ı](https://github.com/muratEfeErgin/cli/pull/1) çalışır GitHub check'i sağlamıyor. Canlı yerel CLI provasında gerçek HTTPie geçmişinden 120 kart ve gerçek D1 veri kümesinden eğitilmiş LR modeli kullanıldı; LLM yolunu özellikle çalıştırmak için `low_threshold = 0.05` geçici yerel ayarı kullanıldı. Bu ayar varsayılan eşik değildir. Tam demo için PR #3'teki Qwen şema hatası giderilmeli, injection senaryosunun model davranışı ayrıca doğrulanmalı ve GitHub Action erişilebilir bir dağıtıma taşınmalıdır.

**Hazırlık gereklilikleri:**
- [ ] Demo PR'ları hazır ve en az 2 kez prova edilmiş
- [ ] Ollama ile çevrimdışı yedek çalışıyor
- [ ] Kayıtlı yedek video (donanım veya Ollama sorununa karşı)
- [ ] Tek sayfalık sonuç grafiği (RQ1 eğrisi + RQ2 sonucu)

---

## 8. Olası Jüri Soruları

### "CodeRabbit veya Copilot code review zaten var. Farkınız ne?"
Üç fark var: Her PR'a LLM çağırmıyoruz (K1); LLM'e reponun kendi geçmiş hatalarını veriyoruz (K2); her şey yerelde çalışıyor, kod dışarı çıkmıyor ve API ücreti yok. K1 ve K2'nin etkisini ablation deneyleriyle (RQ1, RQ2) sayıyla gösteriyoruz.

### "Neden XGBoost/LightGBM? Küçük bir LLM de PR'ın riskli olup olmadığına karar veremez mi?"
Bunu test ettik (RQ1). Klasik model çok daha ucuz, deterministik ve SHAP ile açıklanabilir. Karşılaştırma sonucu da tezde var.

### "Hafızalı versiyonun iyi çıkması sadece prompt uzadığı için olamaz mı?"
Aynı uzunlukta rastgele kartlar veren bir plasebo varyantıyla karşılaştırdık (RQ2). İyileşme hafızanın içeriğinden geliyor.

### "JIT defect prediction zaten var. Yeni olan ne?"
Bu modeller tek başına bir olasılık üretip bırakıyor. Biz bu olasılığı LLM için bir maliyet kapısı olarak, SZZ eşlemelerini de LLM'e bağlam olarak kullanıyoruz. Tahmin, açıklamalı ve somut bir inceleme yorumuna dönüşüyor.

### "SZZ etiketleri gürültülü değil mi?"
Evet. Filtreler uyguluyor, örneklemi elle kontrol ediyor ve elle etiketli alt kümede de raporluyoruz.

### "Gatekeeper hatalı bir PR'ı geçirirse?"
Eşik bütçe–recall eğrisinden bilinçli olarak seçiliyor. Düşük bantta da risk skoru yorum olarak yazılıyor ve `aegis:force` etiketiyle tam inceleme zorlanabiliyor. Aegis insan incelemesinin yerini almıyor, önceliklendiriyor.

### "Veri sızıntısı var mı?"
Hayır. Doğrulama zaman sıralı, hafıza zamansal filtreli ve etiketi henüz oluşmamış son aylar eğitime alınmıyor.

### "LLM bu repoların hatalarını ezberlemiş olamaz mı?"
Olabilir. Model bilgi kesim tarihinden sonraki commit'lerle ayrı bir alt küme oluşturup ayrıca raporluyoruz.

### "Kötü niyetli bir PR, LLM'i kandırıp bulguları gizletebilir mi?"
PR içeriği prompt'ta veri olarak işaretleniyor ve ajanın hiçbir araç yetkisi yok. Çıktı şeması fazladan alan kabul etmiyor; uydurma kanıtlı bulgular düşüyor. Bilinen saldırı kalıpları da modelden bağımsız, deterministik bir dedektörle güvenlik bulgusu olarak raporlanıyor; model kandırılsa bile bu bulgu bastırılamıyor. 14 saldırı örneğiyle regresyon testlerimiz var; demoda canlı gösteriyoruz.

### "PR kodunu CI'da çalıştırmak güvenli mi?"
Aegis PR kodunu çalıştırmıyor, yalnızca diff'i okuyor. `pull_request_target` kullanmıyoruz ve yapılandırma taban daldan okunuyor; bir PR kendi incelemesini gevşetemiyor.

### "İlk kurulum ne kadar sürüyor? Her PR'da tüm geçmiş mi taranıyor?"
Hayır. İlk madencilik ve indeksleme yerelde bir kez yapılıyor ve GitHub Release asset'i olarak yükleniyor. Action bu arşivi indiriyor; her PR'da geçmiş yeniden taranmıyor. Tüm geçmiş üzerinde SZZ, en büyük hedef repoda (scrapy) 4 dakikadan kısa sürüyor.

### "Neden otomatik düzeltme (patch) üretmiyorsunuz?"
Bilinçli bir kapsam kararı. Testle doğrulanmış patch üretimi ayrı bir araştırma problemi (APR) ve güvenilir yapılması için sandbox ile büyük bir benchmark gerekiyor. v1'de katkıyı ölçülebilir iki parçaya (K1, K2) yoğunlaştırdık; patch hattı gelecek çalışma. Mimari buna hazır: bulgular zaten satır ve kanıtla doğrulanmış biçimde üretiliyor.

### "Kullanıcılar bu yorumları gerçekten faydalı buluyor mu?"
Bunu ölçmek için 6–10 geliştiriciyle kör bir kullanıcı çalışması tasarladık (RQ5): Aegis ve PR-Agent yorumları kaynak gizlenerek puanlatılıyor.

### "Geçmişi olmayan yeni bir repoda ne olacak?"
Repolar arası genel model kullanılıyor; hafıza boşsa analiz hafızasız yapılıyor.

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

> Başlangıç listesidir; künyeler tez yazımında doğrulanmalı.

- Śliwerski, Zimmermann, Zeller — *When do changes induce fixes?* (MSR 2005)
- Kamei vd. — *A Large-Scale Empirical Study of Just-in-Time Quality Assurance* (IEEE TSE 2013)
- Spadini, Aniche, Bacchelli — *PyDriller: Python Framework for Mining Software Repositories* (ESEC/FSE 2018)
- Hoang vd. — *DeepJIT: An End-to-End Deep Learning Framework for Just-in-Time Defect Prediction* (MSR 2019)
- Pornprasit, Tantithamthavorn — *JITLine: A Simpler, Better, Faster, Finer-grained Just-In-Time Defect Prediction* (MSR 2021)
- Widyasari vd. — *BugsInPy: A Database of Existing Bugs in Python Programs* (ESEC/FSE 2020)
- Lewis vd. — *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks* (NeurIPS 2020)
