"""Elle etiketleme setleri: örneklem, model paketleri ve inceleme sayfaları (#8, #9).

İki set vardır:

- **szz** (#9): 6 repodan 50 fix → bug-inducing eşlemesi (tüm geçmiş, MA-SZZ). Soru: fix'in
  düzelttiği hatalı satırı bu inducing commit gerçekten yazdı mı?
- **fix** (#8): 6 repodan 200 commit; yarısı sınıflandırıcının fix dediği, yarısı demediği
  commit'ler (precision ve recall için). Sınıflandırıcının kararı pakette ve sayfada yer almaz.
  Soru: bu commit üretim kodundaki bir hatayı düzeltiyor mu?

Akış: `sample` → `packet` (modellerin etiketlemesi için Markdown) → modeller
`<set>-<model>.json` yazar (`{"<no>": [etiket, gerekçe]}`) → `page` (öneriler gösterilen HTML;
kişi kendi kararını verir ve CSV indirir). Raporda yöntem: insan etiketi, LLM önerileri görülerek.

Kullanım:
    uv run python eval/labeling.py sample
    uv run python eval/labeling.py packet
    uv run python eval/labeling.py page [eval/labels/szz-opus.json ...]
"""

import html
import json
import sys
from pathlib import Path
from typing import Any

import polars as pl

from aegis.mining.gitfiles import git
from aegis.mining.szz import review_sample

sys.path.insert(0, str(Path(__file__).parent))
from szz_review import build  # noqa: E402

DATA, REPOS, OUT = Path(".aegis/data"), Path(".aegis/repos"), Path("eval/labels")
SLUGS = (
    "fastapi__fastapi",
    "httpie__cli",
    "psf__black",
    "scrapy__scrapy",
    "tornadoweb__tornado",
    "tqdm__tqdm",
)
SZZ_N, FIX_N, SEED, DIFF_LINES = 50, 200, 13, 80


def _quota(total: int) -> list[int]:
    base, extra = divmod(total, len(SLUGS))
    return [base + (i < extra) for i in range(len(SLUGS))]


def sample() -> None:
    """İki örneklemi `eval/labels/` altına CSV olarak yazar (sabit tohum)."""
    OUT.mkdir(parents=True, exist_ok=True)
    szz = [
        review_sample(DATA / slug, n, SEED).with_columns(pl.lit(slug).alias("repo"))
        for slug, n in zip(SLUGS, _quota(SZZ_N), strict=True)
    ]
    pl.concat(szz).write_csv(OUT / "szz-sample.csv")

    d1 = pl.read_parquet(DATA / "d1.parquet").select("repo", "sha")
    frames = []
    for slug, n in zip(SLUGS, _quota(FIX_N), strict=True):
        commits = pl.read_parquet(DATA / slug / "commits.parquet").join(
            d1.filter(pl.col("repo") == slug).select("sha"), on="sha"
        )
        meta = json.loads((DATA / slug / "meta.json").read_text("utf-8"))
        base = (meta.get("remote_url") or "").removesuffix(".git").rstrip("/")
        half = [n // 2 + n % 2, n // 2]
        for flag, k in zip((True, False), half, strict=True):
            part = commits.filter(pl.col("is_fix") == flag).sample(k, seed=SEED)
            frames.append(
                part.select(
                    pl.lit(slug).alias("repo"),
                    "sha",
                    pl.col("committer_date").dt.date().alias("date"),
                    (pl.lit(f"{base}/commit/") + pl.col("sha")).alias("url"),
                    pl.col("is_fix").alias("classifier"),
                )
            )
    # Sıra karıştırılır: sınıflandırıcının kararı sıradan çıkarılamasın.
    fixes = pl.concat(frames).sample(fraction=1.0, shuffle=True, seed=SEED)
    fixes.write_csv(OUT / "fix-sample.csv")
    print(f"szz: {sum(f.height for f in szz)} eşleme · fix: {fixes.height} commit -> {OUT}")


def szz_items() -> list[dict[str, Any]]:
    sample_csv = OUT / "szz-sample.csv"
    rows = pl.read_csv(sample_csv, infer_schema=False)
    items: list[dict[str, Any]] = []
    for slug in SLUGS:
        part = rows.filter(pl.col("repo") == slug)
        tmp = OUT / f".szz-{slug}.csv"
        part.drop("repo").write_csv(tmp)
        try:
            for it in build(DATA / slug, REPOS / slug, tmp):
                items.append({**it, "repo": slug})
        finally:
            tmp.unlink()
    for i, it in enumerate(items, 1):
        it["no"] = i
    return items


def fix_items() -> list[dict[str, Any]]:
    rows = pl.read_csv(OUT / "fix-sample.csv", infer_schema=False)
    items: list[dict[str, Any]] = []
    for i, row in enumerate(rows.iter_rows(named=True), 1):
        repo = REPOS / row["repo"]
        message = git(repo, "log", "-1", "--format=%B", row["sha"]).strip()
        stat = git(repo, "show", "--numstat", "--format=", row["sha"]).strip().splitlines()
        files = [line.split("\t", 2) for line in stat if line.count("\t") >= 2]
        diff = git(repo, "show", "-U2", "--format=", row["sha"]).splitlines()
        lines = [
            ["add" if t.startswith("+") else "del" if t.startswith("-") else "ctx", t]
            for t in diff[:DIFF_LINES]
            if not t.startswith(("+++", "---", "index ", "diff --git"))
        ]
        items.append(
            {
                "no": i,
                "repo": row["repo"],
                "sha": row["sha"],
                "date": row["date"],
                "url": row["url"],
                "message": message,
                "files": files,
                "diff": lines,
                "truncated": len(diff) > DIFF_LINES,
            }
        )
    return items


SZZ_GUIDE = """# SZZ eşleme kontrolü ({n} eşleme, 6 repo)

Her eşleme: bir **FIX** commit'i ve SZZ'nin, bu fix'in düzelttiği satırları yazan commit olarak
bulduğu bir **INDUCING** commit'i.

Tek soru: *Fix'in düzelttiği hatalı satırı bu INDUCING commit gerçekten yazdı mı?*

- `>` ile işaretli satırlara bak; diğerleri bağlamdır.
- **evet**: INDUCING commit hatalı mantığı ilk kez yazdı ya da anlamını değiştirdi.
- **hayir**: Yalnızca biçim, yorum, isim, taşıma ya da yeniden düzenleme (hata INDUCING'den önce
  de vardı); ya da FIX aslında bir hata düzeltmesi değil.
- **belirsiz**: Elindeki bilgiyle karar veremiyorsan.
"""

FIX_GUIDE = """# Fix-commit kontrolü ({n} commit, 6 repo)

Tek soru: *Bu commit, üretim kodundaki hatalı bir davranışı düzeltiyor mu?*

- **evet**: Yanlış çıktı, çökme, istisna, sızıntı, regresyon, yanlış koşul gibi bir hatayı
  düzeltiyor (testle birlikte gelmesi fark etmez).
- **hayir**: Yeni özellik, yeniden düzenleme, performans iyileştirmesi; yalnızca doküman, yazım
  hatası, test, CI, lint/biçim ya da bağımlılık güncellemesi; geri alma (revert).
- **belirsiz**: Mesaj ve diff'ten karar veremiyorsan.

Diff her commit için ilk {lines} satırla sınırlıdır.
"""

OUTPUT_NOTE = """
## Çıktı

Her madde için etiket ve kısa (bir cümlelik) Türkçe gerekçe. JSON olarak yaz:
`{{"1": ["evet", "gerekçe"], "2": ["hayir", "gerekçe"], ...}}`. Etiketler yalnızca `evet`,
`hayir`, `belirsiz`. Tüm {n} madde için bir etiket olmalı.
"""


def _code(rows: list[list[Any]]) -> list[str]:
    out = []
    for kind, _no, text, hit in rows:
        if kind == "sep":
            out.append("  ...")
            continue
        sign = {"del": "-", "add": "+"}.get(kind, " ")
        out.append(f"{'>' if hit else ' '}{sign} {text}")
    return out


def packet() -> None:
    """Modeller için Markdown paketleri; önceki etiketler ve sınıflandırıcı kararı içermez."""
    szz = szz_items()
    out = [SZZ_GUIDE.format(n=len(szz)), OUTPUT_NOTE.format(n=len(szz))]
    for it in szz:
        out.append(f"\n## {it['no']} · {it['repo']}")
        out.append(f"- FIX: {it['fix_subject']} ({it['fix_date']})")
        out.append(f"- INDUCING: {it['inducing_subject']} ({it['inducing_date']})")
        if not it["sections"]:
            out.append("\n(Satırlar otomatik çıkarılamadı.)")
        for s in it["sections"]:
            out.append(f"\n**Dosya:** `{s['path']}` (inducing'de: `{s['ind_path']}`)")
            out += ["\nFIX:", "```diff", *_code(s["fix"]), "```"]
            out += ["\nINDUCING:", "```diff", *_code(s["inducing"]), "```"]
    (OUT / "szz-packet.md").write_text("\n".join(out) + "\n", "utf-8")

    fixes = fix_items()
    out = [FIX_GUIDE.format(n=len(fixes), lines=DIFF_LINES), OUTPUT_NOTE.format(n=len(fixes))]
    for it in fixes:
        out.append(f"\n## {it['no']} · {it['repo']} · {it['date']}")
        out += ["```text", it["message"], "```"]
        out.append("Dosyalar: " + ", ".join(f"{p} (+{a} −{d})" for a, d, p in it["files"]))
        out += ["```diff", *(t for _, t in it["diff"]), "```"]
        if it["truncated"]:
            out.append("(diff kısaltıldı)")
    (OUT / "fix-packet.md").write_text("\n".join(out) + "\n", "utf-8")
    print(f"paketler: {len(szz)} eşleme, {len(fixes)} commit -> {OUT}")


def _suggest(items: list[dict[str, Any]], files: list[Path]) -> None:
    for path in files:
        model = path.stem.rsplit("-", 1)[-1]
        labels = json.loads(path.read_text("utf-8"))
        for it in items:
            if (s := labels.get(str(it["no"]))) is not None:
                it.setdefault("suggestions", []).append(
                    {"model": model, "label": s[0], "reason": s[1]}
                )


def _write(template: str, title: str, items: list[dict[str, Any]], out: Path) -> None:
    text = (Path(__file__).parent / template).read_text("utf-8")
    page = text.replace("__TITLE__", html.escape(title)).replace(
        "__DATA__", json.dumps(items, ensure_ascii=False).replace("</", "<\\/")
    )
    out.write_text(page, "utf-8")
    print(f"{len(items)} madde -> {out}")


def page(files: list[Path]) -> None:
    szz = szz_items()
    _suggest(szz, [f for f in files if f.name.startswith("szz-")])
    _write("szz_review_template.html", "6 repo", szz, OUT / "szz-review.html")
    fixes = fix_items()
    _suggest(fixes, [f for f in files if f.name.startswith("fix-")])
    _write("fix_review_template.html", "6 repo", fixes, OUT / "fix-review.html")


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "sample":
        sample()
    elif command == "packet":
        packet()
    elif command == "page":
        page([Path(a) for a in sys.argv[2:]])
    else:
        sys.exit(__doc__)
