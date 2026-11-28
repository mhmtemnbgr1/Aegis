"""Aegis Dashboard: yerel, salt okunur web arayüzü (FR-60 – FR-63, FR-66).

`aegis dashboard` ile başlatılır; doğrudan çalıştırmak için:
`AEGIS_ROOT=<repo> streamlit run src/aegis/dashboard/app.py`. Veri `data.py` üzerinden okunur;
bu dosya yalnızca ekranları çizer.
"""

import os
from pathlib import Path

import altair as alt
import polars as pl
import streamlit as st

from aegis.dashboard import data

ROOT = Path(os.environ.get("AEGIS_ROOT", "."))
SHARES = [i / 100 for i in range(5, 101, 5)]


@st.cache_data
def _runs() -> list[dict[str, object]]:
    return data.load_runs([ROOT / data.DATASETS / "d4.jsonl", ROOT / data.RUNS])


@st.cache_data
def _curve(repos: tuple[str, ...]) -> tuple[dict[str, list[float]], int]:
    samples = data.triage_samples(ROOT / data.DATASETS)
    extra = data.llm_triage_scores(ROOT / data.RESULTS)
    curve = data.cost_recall(samples, SHARES, extra, repos)
    return curve, sum(s.repo in repos for s in samples)


@st.cache_data
def _triage_repos() -> list[str]:
    return sorted({s.repo for s in data.triage_samples(ROOT / data.DATASETS)})


@st.cache_resource
def _cards() -> list[data.CardEntry]:
    return data.load_cards(ROOT / data.DATASETS, ROOT / ".aegis/data")


def overview() -> None:
    st.header("Genel bakış")
    st.caption(
        "Gerçek PR'larda Aegis çalıştırmaları: D4 veri seti ve varsa yerel `.aegis/runs.jsonl`."
    )
    runs = _runs()
    if not runs:
        st.info("Çalıştırma kaydı bulunamadı.")
        return
    totals = data.run_totals(runs)
    cols = st.columns(5)
    cols[0].metric("Çalıştırma", totals["runs"])
    cols[1].metric("PR", totals["prs"])
    cols[2].metric("LLM'e yönlendirilen", f"%{100 * totals['llm_share']:.0f}")
    cols[3].metric("Bulgu", totals["findings"])
    cols[4].metric("Ortalama süre", f"{totals['mean_seconds']:.1f} sn")

    left, right = st.columns(2)
    left.subheader("Risk bantları")
    bands = [b for b in ("low", "medium", "high") if b in totals["bands"]]
    left.bar_chart(
        pl.DataFrame({"bant": bands, "sayi": [totals["bands"][b] for b in bands]}),
        x="bant",
        y="sayi",
        x_label="Risk bandı",
        y_label="Çalıştırma",
        sort=False,
    )
    right.subheader("Sonuç durumları")
    right.bar_chart(
        pl.DataFrame(
            {"durum": list(totals["statuses"]), "sayi": list(totals["statuses"].values())}
        ),
        x="durum",
        y="sayi",
        x_label="Durum",
        y_label="Çalıştırma",
    )

    st.subheader("Çalıştırmalar")
    table = pl.DataFrame(
        [
            {
                "tarih": str(r.get("started_at", ""))[:16].replace("T", " "),
                "repo": r.get("repo"),
                "PR": r.get("pr"),
                "risk": r.get("risk_score"),
                "bant": r.get("risk_band"),
                "durum": r.get("status"),
                "bulgu": r.get("findings"),
                "satır": r.get("changed_lines"),
                "süre (sn)": r.get("duration_seconds"),
            }
            for r in runs
        ]
    )
    st.dataframe(table, hide_index=True, use_container_width=True)


def gatekeeper() -> None:
    st.header("Gatekeeper")
    st.caption(
        "RQ1 örneklemi: 25 zaman penceresinden 1.250 gerçek PR. LLM bütçesi, PR'ların ne kadarının "
        "LLM'e gönderileceğidir; eğri her bütçede yakalanan hatalı PR oranını gösterir "
        "(pencere ortalaması)."
    )
    repos = _triage_repos()
    if not repos:
        st.info("`eval/datasets/rq1-triage.jsonl` bulunamadı.")
        return
    chosen = st.multiselect("Repolar", repos, default=repos)
    if not chosen:
        st.warning("En az bir repo seçin.")
        return
    curve, n = _curve(tuple(chosen))
    budget = st.slider("LLM bütçesi (PR'ların yüzdesi)", 5, 100, 40, step=5)
    i = SHARES.index(budget / 100)

    cols = st.columns(len(curve))
    for col, (name, values) in zip(cols, curve.items(), strict=True):
        col.metric(name, f"%{100 * values[i]:.1f}", help="Yakalanan hatalı PR oranı")
    st.caption(f"{n} PR. Rastgele seçim aynı bütçede %{budget} yakalar.")

    rows = [
        {"pay": round(100 * share), "yontem": name, "recall": round(100 * values[j], 1)}
        for name, values in [*curve.items(), ("Rastgele", SHARES)]
        for j, share in enumerate(SHARES)
    ]
    # Vega alan adlarında parantez ve kesme işareti sorun çıkarır; başlıklar ayrıca verilir.
    axis = alt.Scale(domain=[0, 100])
    lines = (
        alt.Chart(pl.DataFrame(rows))
        .mark_line()
        .encode(
            x=alt.X("pay:Q", title="LLM'e gönderilen PR'lar (%)", scale=axis),
            y=alt.Y("recall:Q", title="Yakalanan hatalı PR'lar (%)", scale=axis),
            color=alt.Color("yontem:N", title="Yöntem"),
            tooltip=["yontem:N", "pay:Q", "recall:Q"],
        )
    )
    rule = alt.Chart(pl.DataFrame({"pay": [budget]})).mark_rule(strokeDash=[4, 4]).encode(x="pay:Q")
    st.altair_chart((lines + rule).properties(height=420), use_container_width=True)


def memory() -> None:
    st.header("Hafıza")
    entries = _cards()
    st.caption(
        f"{len(entries)} hata kartı (D2 kartları ve varsa yerel durum arşivi). Dosya, fonksiyon, "
        "özet, issue numarası ya da kart kimliğiyle arayın."
    )
    if not entries:
        st.info("Hata kartı bulunamadı.")
        return
    left, right = st.columns([3, 1])
    query = left.text_input("Ara", placeholder="ör. pool.py, ConnectionPool, #89")
    repos = sorted({e.repo for e in entries})
    repo = right.selectbox("Repo", ["tümü", *repos])
    hits = data.search_cards(entries, query, None if repo == "tümü" else repo)
    shown = hits[:50]
    more = f"; ilk {len(shown)} gösteriliyor" if len(hits) > len(shown) else ""
    st.write(f"{len(hits)} sonuç{more}.")
    for e in shown:
        c = e.card
        issue = f" · #{c.issue.number}" if c.issue else ""
        with st.expander(f"{c.id} · {e.repo}{issue} · {c.fix_date:%Y-%m-%d} · {c.summary[:80]}"):
            st.markdown(f"**Düzeltme commit'i:** `{c.fix_sha[:12]}`")
            if c.files:
                st.markdown("**Dosyalar:** " + ", ".join(f"`{f}`" for f in c.files))
            if c.functions:
                st.markdown("**Fonksiyonlar:** " + ", ".join(f"`{f}`" for f in c.functions))
            if c.before or c.after:
                a, b = st.columns(2)
                a.markdown("**Önce**")
                a.code(c.before or "(boş)", language="python")
                b.markdown("**Sonra**")
                b.code(c.after or "(boş)", language="python")
            elif c.fix_diff:
                st.code(c.fix_diff, language="diff")


def experiments() -> None:
    st.header("Deneyler")
    summaries = data.result_summaries(ROOT / data.RESULTS, ROOT / "docs")
    if not summaries:
        st.info("Henüz deney özeti yok.")
        return
    title = st.selectbox("Özet", list(summaries))
    text = summaries[title].read_text(encoding="utf-8")
    # Göreli görsel yolları tarayıcıda çözülmez; yalnızca metin ve tablolar gösterilir.
    st.markdown("\n".join(line for line in text.splitlines() if not line.startswith("![")))


PAGES = {
    "Genel bakış": overview,
    "Gatekeeper": gatekeeper,
    "Hafıza": memory,
    "Deneyler": experiments,
}


def main() -> None:
    st.set_page_config(page_title="Aegis Dashboard", layout="wide")
    st.sidebar.title("Aegis")
    page = st.sidebar.radio("Ekran", list(PAGES), label_visibility="collapsed")
    # Yalnızca klasör adı: tam yol kullanıcı adını içerir ve demoda ekranda görünür.
    st.sidebar.caption(f"Kaynak: `{ROOT.resolve().name}`")
    PAGES[page]()


main()
