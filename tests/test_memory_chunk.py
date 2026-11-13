"""Fonksiyon düzeyinde parçalama (#23)."""

from aegis.memory.chunk import FunctionSpan, changed_lines, extract, functions, module_name, touched

SOURCE = """\
import os


def top(x):
    return x + 1


class Pool:
    class Conn:
        def close(self):
            pass

    @staticmethod
    @cache
    def make():
        def helper():
            return 1
        return helper()

    async def release(self, conn):
        await conn.close()
"""


def test_module_name() -> None:
    assert module_name("app/db/pool.py") == "app.db.pool"
    assert module_name("pkg/__init__.py") == "pkg"
    assert module_name("setup.py") == "setup"


def test_qualified_names_for_nested_classes_and_methods() -> None:
    spans = functions(SOURCE, "app/db/pool.py")
    assert [(s.qualname, s.start, s.end) for s in spans] == [
        ("app.db.pool.top", 4, 5),
        ("app.db.pool.Pool.Conn.close", 10, 11),
        ("app.db.pool.Pool.make", 13, 18),  # dekoratörler dahil
        ("app.db.pool.Pool.make.helper", 16, 17),
        ("app.db.pool.Pool.release", 20, 21),
    ]


def test_syntax_error_is_skipped() -> None:
    assert functions("def broken(:\n    pass\n", "x.py") == []


def test_touched_picks_innermost_function() -> None:
    spans = functions(SOURCE, "m.py")
    names = [s.qualname for s in touched(spans, {17, 21, 1})]
    assert names == ["m.Pool.make.helper", "m.Pool.release"]  # satır 1 (import) fonksiyonda değil


def test_changed_lines_from_unified_diff() -> None:
    diff = "@@ -5,2 +5,3 @@\n-a\n-b\n+a\n+b\n+c\n@@ -10,0 +12 @@\n+d\n@@ -20 +22,0 @@\n-e\n"
    old, new = changed_lines(diff)
    assert old == {5, 6, 10, 20}
    assert new == {5, 6, 7, 12, 22}


def test_extract_truncates() -> None:
    span = FunctionSpan("m.f", 1, 5)
    text = extract("a\nb\nc\nd\ne\n", span, 2)
    assert text == "a\nb\n# ... (3 satır kırpıldı)"


def test_extract_focuses_on_changed_lines() -> None:
    source = "\n".join(["def f():"] + [f"    x{i} = {i}" for i in range(1, 40)]) + "\n"
    span = FunctionSpan("m.f", 1, 40)
    text = extract(source, span, 6, focus={30}, context=2)
    assert text.splitlines() == [
        "def f():",
        "    # ...",
        "    x27 = 27",
        "    x28 = 28",
        "    x29 = 29",
        "    x30 = 30",
        "    x31 = 31",
        "    # ...",
    ]
