"""Fonksiyon düzeyinde parçalama: `ast` ile nitelikli adlar ve satır aralıkları (FR-21, #23).

Hafıza kartları ve sorgular fonksiyon düzeyindedir. Her fonksiyon/metot için nitelikli ad
(`paket.modül.Sınıf.İçSınıf.metot`), başlangıç ve bitiş satırı çıkarılır; diff'te değişen satırlar
bu aralıklara eşlenir. Dekoratörler fonksiyona dahildir. Sözdizimi hatalı dosyalar çökmeden boş
sonuç verir.
"""

import ast
import re
from dataclasses import dataclass
from pathlib import PurePosixPath

_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


@dataclass(frozen=True)
class FunctionSpan:
    qualname: str
    """Modül yolu dahil nitelikli ad, ör. `app.db.pool.ConnectionPool.release`."""
    start: int
    end: int
    """1 tabanlı, kapsayıcı satır aralığı (dekoratörler dahil)."""


def module_name(path: str) -> str:
    """`app/db/pool.py` → `app.db.pool`; `pkg/__init__.py` → `pkg`."""
    parts = list(PurePosixPath(path).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def functions(source: str, path: str = "") -> list[FunctionSpan]:
    """Dosyadaki tüm fonksiyon ve metotlar (iç içe olanlar dahil), başlangıç satırına göre."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    prefix = module_name(path) if path else ""
    out: list[FunctionSpan] = []

    def visit(node: ast.AST, scope: list[str]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                visit(child, [*scope, child.name])
            elif isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                start = min([child.lineno, *(d.lineno for d in child.decorator_list)])
                name = ".".join(p for p in (prefix, *scope, child.name) if p)
                out.append(FunctionSpan(name, start, child.end_lineno or child.lineno))
                visit(child, [*scope, child.name])

    visit(tree, [])
    return sorted(out, key=lambda f: (f.start, -f.end))


def touched(spans: list[FunctionSpan], lines: set[int]) -> list[FunctionSpan]:
    """Değişen satırları içeren en içteki fonksiyonlar (iç içe olanlarda dıştaki tekrarlanmaz)."""
    hit: dict[str, FunctionSpan] = {}
    for line in lines:
        inner = [s for s in spans if s.start <= line <= s.end]
        if inner:
            best = min(inner, key=lambda s: s.end - s.start)
            hit[best.qualname] = best
    return sorted(hit.values(), key=lambda s: s.start)


def changed_lines(diff: str) -> tuple[set[int], set[int]]:
    """`git diff -U0` çıktısından (eski sürümde silinen, yeni sürümde eklenen) satır numaraları.

    Yalnızca ekleme yapan bir hunk, eski sürümde ekleme noktasındaki satırı da işaretler; böylece
    bir fonksiyonun gövdesine satır eklenmesi o fonksiyonun "önceki" halini de getirir.
    """
    old: set[int] = set()
    new: set[int] = set()
    for line in diff.splitlines():
        m = _HUNK.match(line)
        if not m:
            continue
        o_start, o_len = int(m.group(1)), int(m.group(2) or 1)
        n_start, n_len = int(m.group(3)), int(m.group(4) or 1)
        old.update(range(o_start, o_start + o_len) if o_len else [max(o_start, 1)])
        new.update(range(n_start, n_start + n_len) if n_len else [max(n_start, 1)])
    return old, new


def extract(
    source: str, span: FunctionSpan, max_lines: int, focus: set[int] | None = None, context: int = 4
) -> str:
    """Fonksiyonun kaynak kodu; `max_lines`'tan uzunsa kırpılır.

    Kırpmada imza satırı ve değişen satırların (`focus`) çevresindeki `context` satır korunur;
    atlanan bölümler `# ...` ile gösterilir. `focus` yoksa baştan kırpılır.
    """
    all_lines = source.splitlines()
    lines = all_lines[span.start - 1 : span.end]
    if len(lines) <= max_lines:
        return "\n".join(lines)
    hits = sorted(n - span.start for n in (focus or set()) if span.start <= n <= span.end)
    if not hits:
        kept = [*lines[:max_lines], f"# ... ({len(lines) - max_lines} satır kırpıldı)"]
        return "\n".join(kept)
    wanted: set[int] = {0}
    for h in hits:
        for k in range(max(0, h - context), min(len(lines), h + context + 1)):
            if len(wanted) >= max_lines:
                break
            wanted.add(k)
    out: list[str] = []
    prev = -1
    for k in sorted(wanted):
        if k != prev + 1:
            out.append("    # ...")
        out.append(lines[k])
        prev = k
    if prev != len(lines) - 1:
        out.append("    # ...")
    return "\n".join(out)
