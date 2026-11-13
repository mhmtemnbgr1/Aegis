## Example 1 (a real defect)

<pr_diff>
### app/db/pool.py (modified)
@@ -40,4 +40,6 @@ class ConnectionPool:
   40     def release(self, conn):
      -        self.free.append(conn)
   41 +        if conn.closed:
   42 +            return
   43 +        self.free.append(conn)
   44         self.size -= 1
</pr_diff>

Output:
{"summary": "Kapalı bağlantılar için havuz sayacı azaltılmıyor.", "findings": [{"file": "app/db/pool.py", "line": 41, "end_line": 42, "category": "resource-leak", "severity": "high", "confidence": 0.8, "title": "Kapalı bağlantıda size azaltılmadan dönülüyor", "explanation": "conn.closed ise fonksiyon erken dönüyor ve self.size -= 1 çalışmıyor; havuz zamanla dolu görünür ve yeni bağlantı verilmez.", "evidence": "if conn.closed:\n    return", "memory_refs": []}]}

## Example 2 (nothing to report)

<pr_diff>
### app/utils/text.py (modified)
@@ -10,3 +10,3 @@ def slugify(value):
   10     value = value.strip().lower()
      -    return re.sub(r"[^a-z0-9]+", "-", value)
   11 +    return re.sub(r"[^a-z0-9]+", "-", value).strip("-")
</pr_diff>

Output:
{"summary": "Değişiklik baştaki ve sondaki tireleri temizliyor; bir hata görülmedi.", "findings": []}
