"""İnceleme sayfasından indirilen CSV'den SZZ eşleme doğruluğunu hesaplar (#9).

Doğruluk = evet / (evet + hayir); belirsizler paydadan çıkarılır ve ayrıca raporlanır.

Kullanım:
    uv run python eval/score_labels.py eval/labels/szz-kontrol-tqdm__tqdm.csv
"""

import csv
import sys
from collections import Counter
from pathlib import Path

LABELS = ("evet", "hayir", "belirsiz")


def score(path: Path) -> Counter[str]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return Counter((row.get("correct") or "").strip() for row in csv.DictReader(f))


def main() -> None:
    counts = score(Path(sys.argv[1]))
    total = sum(counts.values())
    empty = counts.pop("", 0)
    unknown = sorted(k for k in counts if k not in LABELS)
    if unknown:
        sys.exit(f"Tanınmayan etiket(ler): {', '.join(unknown)}")
    yes, no, maybe = (counts[k] for k in LABELS)
    print(f"{total} eşleme · evet {yes} · hayır {no} · belirsiz {maybe} · boş {empty}")
    if yes + no:
        print(f"Doğruluk (belirsizler hariç): {yes}/{yes + no} = {yes / (yes + no):.0%}")
    if empty:
        print("Uyarı: işaretlenmemiş eşleme var.")


if __name__ == "__main__":
    main()
