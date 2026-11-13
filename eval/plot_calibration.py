"""Kalibrasyon eğrilerini (reliability diagram) SVG olarak çizer (#18).

Girdi: `aegis train --report <dizin>/<repo>-<yöntem>.json` ile üretilmiş raporlar; yöntem
`none`, `sigmoid` veya `isotonic`. Her repo için bir panel; her yöntem bir çizgi. Köşegen
mükemmel kalibrasyondur. Ek bağımlılık gerekmez (matplotlib yok).

Kullanım:
    uv run python eval/plot_calibration.py eval/reports/calibration lr \
        eval/reports/calibration-lr.svg
"""

import json
import sys
from html import escape
from pathlib import Path

METHODS = {"none": "#9a9a9a", "sigmoid": "#2563eb", "isotonic": "#d97706"}
LABELS = {"none": "kalibrasyonsuz", "sigmoid": "sigmoid (Platt)", "isotonic": "isotonic"}
SIZE, PAD, GAP, COLS = 220, 34, 26, 3


def panel(x0: float, y0: float, repo: str, curves: dict[str, list[list[float]]]) -> list[str]:
    def px(v: float) -> float:
        return x0 + PAD + v * SIZE

    def py(v: float) -> float:
        return y0 + PAD + (1 - v) * SIZE

    out = [
        f'<rect x="{px(0)}" y="{py(1)}" width="{SIZE}" height="{SIZE}" fill="none" stroke="#ccc"/>',
        f'<line x1="{px(0)}" y1="{py(0)}" x2="{px(1)}" y2="{py(1)}" stroke="#ccc" '
        'stroke-dasharray="4 4"/>',
        f'<text x="{px(0.5)}" y="{y0 + PAD - 10}" text-anchor="middle" font-size="13" '
        f'font-weight="600">{escape(repo)}</text>',
    ]
    for t in (0, 0.5, 1):
        out.append(
            f'<text x="{px(t)}" y="{py(0) + 14}" text-anchor="middle" font-size="10">{t:g}</text>'
        )
        out.append(
            f'<text x="{px(0) - 6}" y="{py(t) + 3}" text-anchor="end" font-size="10">{t:g}</text>'
        )
    for method, rows in curves.items():
        if not rows:
            continue
        points = " ".join(f"{px(p):.1f},{py(r):.1f}" for p, r, _ in rows)
        color = METHODS[method]
        out.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2"/>')
        for p, r, n in rows:
            radius = min(6.0, 1.5 + n**0.5 / 6)
            out.append(
                f'<circle cx="{px(p):.1f}" cy="{py(r):.1f}" r="{radius:.1f}" fill="{color}"/>'
            )
    return out


def main() -> None:
    reports, model, out = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
    data: dict[str, dict[str, list[list[float]]]] = {}
    for path in sorted(reports.glob("*.json")):
        report = json.loads(path.read_text("utf-8"))
        method = path.stem.rsplit("-", 1)[-1]
        if method in METHODS and model in report["models"]:
            curves = data.setdefault(report["repo"], {})
            curves[method] = report["models"][model]["reliability"]
    repos = sorted(data)
    if not repos:
        sys.exit(f"{reports} altında {model} için rapor yok")
    cell = SIZE + 2 * PAD + GAP
    rows = (len(repos) + COLS - 1) // COLS
    width, height = COLS * cell, rows * cell + 50
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'font-family="sans-serif"><rect width="100%" height="100%" fill="white"/>'
    ]
    for i, repo in enumerate(repos):
        parts += panel((i % COLS) * cell, (i // COLS) * cell, repo, data[repo])
    y = rows * cell + 20
    x = 20.0
    for method, color in METHODS.items():
        parts.append(f'<rect x="{x}" y="{y - 10}" width="14" height="4" fill="{color}"/>')
        parts.append(f'<text x="{x + 20}" y="{y - 4}" font-size="12">{LABELS[method]}</text>')
        x += 170
    parts.append(
        f'<text x="{width - 20}" y="{y - 4}" text-anchor="end" font-size="11" fill="#555">'
        f"{escape(model)} · x: tahmin edilen olasılık, y: gerçek hatalı payı (test)</text>"
    )
    parts.append("</svg>")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(parts), "utf-8")
    print(f"{len(repos)} repo -> {out}")


if __name__ == "__main__":
    main()
