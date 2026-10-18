# Olası Jüri Soruları ve Cevapları

### "Acil bir prod hotfix atılması gerekirse ne olacak?"
`git push --no-verify` veya `AEGIS_SKIP=1` ile inceleme tamamen atlanır. Ayrıca etkileşimli ekranda `[I] Ignore and push anyway` seçeneği vardır. Atlamalar yerel log'a yazılır.

### "Kodumuz üçüncü taraf bir sunucuya mı gidiyor?"
Yalnızca kullanıcının seçtiği sağlayıcıya. `provider = "ollama"` ile tamamen çevrimdışı çalışır. Secret içeren satırlar her durumda maskelenir ve LLM'e gönderilmez.

### "LLM yanlış alarm verirse geliştirici aracı silmez mi?"
Push yalnızca `critical` severity **ve** `confidence ≥ 0.8` bulgularda engellenir. Bulgunun dayandığı satır diff'te birebir yoksa bulgu düşürülür. Bu katmanların etkisi benchmark'ta ölçülmüştür (bkz. Faz 5).

### "API çöker veya internet yoksa push kilitlenir mi?"
Hayır. Fail-open prensibi: aracın kendi hatası push'u asla engellemez; sadece uyarı basılır.

### "40 dosyalık bir push'ta maliyet ne olur?"
Token bütçesi, dosya önceliklendirme ve chunking ile sınırlandırılır. İncelenmeyen dosyalar kullanıcıya raporlanır.

### "Neden gitleaks / Semgrep yetmiyor?"
Onlar kalıp tabanlıdır; iş mantığı hatalarını yakalayamaz. Aegis deterministik kontrolleri önce çalıştırır, LLM'i yalnızca bu araçların göremediği mantık hataları için kullanır.

> Bu dosya proje ilerledikçe güncellenecektir.
