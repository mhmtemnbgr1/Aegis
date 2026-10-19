# Olası Jüri Soruları ve Cevapları

### "CodeRabbit veya Copilot code review zaten var. Farkınız ne?"
Üç fark var: (1) Her PR'a LLM çağırmıyoruz. Bir ML gatekeeper düşük riskli PR'ları eliyor ve tasarrufu ölçüyoruz (RQ1). (2) LLM'e reponun kendi geçmiş hatalarını, bağlı issue ve düzeltmeleriyle birlikte veriyoruz (RQ2). (3) Önerilerimizi testle doğruluyoruz. Doğrulanmayan patch suggestion olarak yayınlanmıyor (RQ3).

### "JIT defect prediction zaten yıllardır var. Yeni olan ne?"
Bu modeller tek başına bir olasılık üretip bırakıyor. Biz bu olasılığı LLM için bir **maliyet kapısı** olarak kullanıyor, SZZ'nin ürettiği fix–inducing eşleşmelerini de LLM'e **bağlam** olarak veriyoruz. Yani tahmin, açıklama ve düzeltmeye dönüşüyor.

### "SZZ etiketleri gürültülü değil mi?"
Evet, literatürde bilinen bir sorun. Boşluk/yorum değişikliklerini, merge commit'lerini ve çok büyük commit'leri eliyor, rastgele bir örneklemi elle kontrol edip hata oranını raporluyoruz. Bu konu tezde geçerlilik tehditleri altında tartışılıyor.

### "Gatekeeper hatalı bir PR'ı 'düşük risk' diye geçirirse ne olacak?"
Eşiği bilinçli olarak seçiyoruz: bütçe–recall eğrisinde "PR'ların %X'i LLM'e gider, hatalı değişikliklerin %Y'si yakalanır" dengesini gösteriyoruz. Düşük bantta da risk skoru ve gerekçesi yorum olarak yazılıyor. `aegis:force` etiketiyle tam inceleme zorlanabiliyor. Aegis insan incelemesinin yerini almıyor, onu önceliklendiriyor.

### "Model eğitimi ve değerlendirmesinde geleceği görme (veri sızıntısı) var mı?"
Hayır. Doğrulama zaman sıralı, rastgele değil. Hafızadan yalnızca PR tarihinden önceki hata kartları getiriliyor. Etiketleri henüz oluşmamış olabilecek son aylar eğitimden çıkarılıyor.

### "LLM, BugsInPy'deki düzeltmeleri zaten ezberlemiş olamaz mı?"
Olabilir. Bunun için modelin bilgi kesim tarihinden sonraki commit'lerden ayrı bir alt küme oluşturup sonuçları ayrıca raporluyoruz.

### "LLM yanlış ya da zararlı bir patch üretirse?"
Patch önce deterministik bir doğrulayıcıdan geçiyor: uygulanabilirlik, lint, mevcut testler ve hatayı yeniden üreten yeni test. Yalnızca `verified` patch'ler tek tıklık suggestion olarak çıkıyor. Hiçbir şey otomatik merge edilmiyor; son karar geliştiricide.

### "PR'daki kodu CI'da çalıştırmak güvenli mi?"
`pull_request_target` kullanmıyoruz. Testler ağsız, kaynak sınırlı bir Docker sandbox'ta ve gizli anahtarlar olmadan koşuyor. Fork PR'larında bulut LLM anahtarı bulunmadığı için yalnızca gatekeeper ve yerel model çalışıyor.

### "Geçmişi olmayan yeni bir repoda ne olacak?"
Diğer repolarda eğitilmiş genel (cross-project) model kullanılıyor. Hafıza boşsa analiz hafızasız yapılıyor. Repo büyüdükçe artımlı madencilikle her ikisi de iyileşiyor.

### "Kodumuz üçüncü taraf bir sunucuya mı gidiyor?"
Yalnızca seçilen sağlayıcıya ve yalnızca gatekeeper'ı geçen PR'larda. Ollama ve yerel embedding modeliyle tamamen çevrimdışı çalışabiliyor.

### "Neden LangGraph gibi hazır bir ajan çerçevesi kullanmadınız?"
Zincir kısa ve sabit (analiz → düzeltme → test → doğrulama). Pydantic üzerinde kendi küçük durum makinemizi yazmak bağımlılığı azaltıyor, her adımı birim testle doğrulanabilir kılıyor ve karar akışını şeffaf tutuyor.

### "API çökerse PR kilitlenir mi?"
Hayır. Fail-open prensibi var: aracın kendi hatası PR'ı bloklamıyor. Check "neutral" sonuçlanıyor ve bir uyarı yorumu bırakılıyor.

> Bu dosya proje ilerledikçe güncellenecektir.
