"""Fix sınıflandırıcısı varyantlarını #8 etiketleriyle karşılaştırır.

Varyantlar yalnızca fix sayılanları azaltır (dışlama kalıbı ekler ya da anahtar kelimeyi başlıkta
arar), bu yüzden fix-olmayan tabakadaki kaçırılan fix'ler değişmez. Precision, sınıflandırıcının
fix dediği örneklem commit'lerinde; recall popülasyon paylarıyla ağırlıklandırılarak hesaplanır.
Ayar aynı 200 commit üzerinde yapıldığı için sonuçlar iyimserdir; yeni bir örneklemde
doğrulanmalıdır.

Kullanım:
    uv run python eval/tune_fix.py eval/labels/fix-kontrol.csv
"""

import sys
from pathlib import Path

import polars as pl

from aegis.config import MiningConfig
from aegis.mining.fixes import FixClassifier

BASELINE_EXCLUDES = MiningConfig().fix_exclude_patterns[:14]
"""#8 öncesindeki 14 dışlama kalıbı; #8'den çıkan kalıplar artık config varsayılanında."""


def variants() -> dict[str, FixClassifier]:
    excl = MiningConfig()
    base = excl.model_copy(update={"fix_exclude_patterns": BASELINE_EXCLUDES})
    return {
        "mevcut": FixClassifier(base),
        "+dışlama": FixClassifier(excl),
        "+dışlama +başlık": FixClassifier(excl.model_copy(update={"fix_subject_only": True})),
    }


def main() -> None:
    labels = pl.read_csv(sys.argv[1], infer_schema=False).select("repo", "sha", "correct")
    sample = pl.read_csv("eval/labels/fix-sample.csv", infer_schema=False).select(
        "repo", "sha", pl.col("classifier") == "true"
    )
    rows = labels.join(sample, on=["repo", "sha"]).filter(pl.col("correct") != "belirsiz")
    d1 = pl.read_parquet(".aegis/data/d1.parquet").select("repo", "sha")
    pops = {
        repo: pl.read_parquet(Path(".aegis/data") / repo / "commits.parquet").join(
            d1.filter(pl.col("repo") == repo).select("sha"), on="sha"
        )
        for repo in sorted(set(rows["repo"]))
    }
    messages = {
        (r, s): m for r, p in pops.items() for s, m in p.select("sha", "message").iter_rows()
    }

    print("| Varyant | Precision | Recall (ağırlıklı) | Popülasyonda fix |")
    print("| --- | --- | --- | --- |")
    for name, clf in variants().items():
        tp = fp = 0
        w_tp = w_fn = 0.0
        n_fix_total = 0
        for repo, pop in pops.items():
            pred = [clf.classify(m).is_fix for m in pop["message"]]
            n_fix = sum(pred)
            n_fix_total += n_fix
            n_other = len(pred) - n_fix
            part = rows.filter(pl.col("repo") == repo)
            pos = part.filter(pl.col("classifier"))
            keep = [clf.classify(messages[(repo, s)]).is_fix for s in pos["sha"]]
            truth = (pos["correct"] == "evet").to_list()
            tp += sum(k and t for k, t in zip(keep, truth, strict=True))
            fp += sum(k and not t for k, t in zip(keep, truth, strict=True))
            # Yeni sınıflandırıcıda fix sayılmayan örneklem commit'leri: eski fix-olmayan tabaka
            # ile eski fix tabakasından düşenler. Kaçırılan oranı tabaka bazında ağırlıklandırılır.
            kept = sum(keep)
            if kept:
                w_tp += n_fix * sum(k and t for k, t in zip(keep, truth, strict=True)) / kept
            neg = part.filter(~pl.col("classifier"))
            dropped = [t for k, t in zip(keep, truth, strict=True) if not k]
            miss_old = (neg["correct"] == "evet").sum() / max(neg.height, 1)
            old_fix = int(pop["is_fix"].sum())
            old_other = pop.height - old_fix
            dropped_rate = sum(dropped) / len(keep) if keep else 0.0
            w_fn += old_other * miss_old + old_fix * dropped_rate
            _ = n_other
        precision = tp / max(tp + fp, 1)
        recall = w_tp / max(w_tp + w_fn, 1e-9)
        print(
            f"| {name} | {tp}/{tp + fp} = %{100 * precision:.0f} | "
            f"%{100 * recall:.0f} | {n_fix_total} |"
        )


if __name__ == "__main__":
    main()
