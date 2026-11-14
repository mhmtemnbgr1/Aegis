# Demo (#50)

`httpie/cli` fork'unda dört PR ile canlı gösterim (docs/presentation.md §7). Demo LLM olmadan da
çalışır: gatekeeper, hafıza ve injection dedektörü deterministiktir. Ollama sunucusu verilirse
(`ollama-host`) analiz yorumu da eklenir.

| Dal | Senaryo | Yerel provada |
| --- | --- | --- |
| `demo/1-typo` | README yazım düzeltmesi | risk 0,00 (düşük) · LLM çağrılmaz |
| `demo/2-feature` | `Retry-After` desteği (2 çekirdek dosya) | risk 0,08 (yüksek) · nedenler ve ilgili geçmiş hatalar |
| `demo/3-regression` | httpie'nin 2023'te düzelttiği hatayı (44d3cff) geri getirir | risk 0,02 (orta) · hafızanın **ilk** kartı tam o fix: `BC-44d3cff03f` |
| `demo/4-injection` | `shell=True` + "ignore previous instructions" yorumu | risk 0,06 (yüksek) · deterministik injection bulgusu |

Bantlar bütçeden: PR'ların en fazla %40'ı LLM'e gider (`max_llm_pr_ratio = 0.4`, RQ1'in maliyet
odaklı noktası). PR yorumu önizlemeleri: `eval/demo/previews/`.

## 1. Yerel hazırlık ve prova (GitHub'a bir şey göndermez)

```bash
uv run python eval/demo/make_demo.py kur     # .aegis/demo/httpie-cli + dört dal
uv run python eval/demo/make_demo.py prova   # her dal için review --no-llm, önizlemeler
```

Ön koşul: `httpie__cli` için madencilik, `aegis index`, `aegis dataset` ve `aegis train` yapılmış olmalı.

## 2. Fork'ta canlı demo (elle; GitHub hesabında değişiklik yapar)

`KULLANICI` GitHub kullanıcı adınız; `GITHUB_TOKEN` repo yazma izinli bir token.

```bash
gh repo fork httpie/cli --clone=false                      # 1. fork
cd .aegis/demo/httpie-cli
git remote add fork https://github.com/KULLANICI/cli.git
git push fork master demo/1-typo demo/2-feature demo/3-regression demo/4-injection
cd ../../..
aegis publish-state .aegis/demo/httpie-cli --as KULLANICI__cli   # 2. durum arşivi
gh pr create -R KULLANICI/cli -B master -H demo/1-typo -t "Clarify feature list in README" -b ""
# ... diğer üç dal için de (aynı başlıklar commit mesajlarında)
```

Fork'ta Actions'ın açık olması gerekir (fork'larda varsayılan kapalıdır: Actions sekmesi → etkinleştir).
`publish-state --as` arşivi fork'un kimliğiyle paketler; Action onu `aegis-state` Release'inden alır.
`master` dalındaki `.github/workflows/aegis.yml` ve `.aegis.toml` demo betiğiyle gelir.

## 5. adım: maliyet karşılaştırması

"Her PR'a LLM" ile Aegis farkı `docs/results.md` §4'teki maliyet–recall eğrisi ve işletme
noktalarından gösterilir (`docs/figures/rq1-curve.svg`).
