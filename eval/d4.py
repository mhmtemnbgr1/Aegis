"""D4: Aegis'in gerçek PR'lardaki çalıştırmaları (dogfooding ve demo; #51, #56).

Action her PR çalıştırmasında `runs.jsonl` kaydını artifact olarak yükler (`upload-runs`). Bu
betik, iki repodaki (Aegis'in kendisi ve demo fork'u) bu artifact'ları indirir, her kaydı ilgili
PR ile eşleştirir ve PR'daki Aegis özet yorumunun 👍/👎 tepkilerini ve satır yorumu sayısını ekler.

    uv run python eval/d4.py topla      # → eval/datasets/d4.jsonl (GitHub CLI oturumu gerekir)

Özet tablo `eval/results.py` ile `docs/results.md` içine yazılır. Artifact'lar 90 gün saklanır;
daha eski çalıştırmalar toplanamaz.
"""

import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

REPOS = ("mhmtemnbgr1/Aegis", "mhmtemnbgr1/cli")
OUT = Path("eval/datasets/d4.jsonl")
MARKER = "<!-- aegis:summary -->"


def gh(*args: str) -> bytes:
    return subprocess.run(["gh", "api", *args], check=True, capture_output=True).stdout


def gh_json(*args: str) -> Any:
    return json.loads(gh(*args))


def paged(path: str) -> list[dict[str, Any]]:
    """`--paginate` ile tüm sayfalar; dizi döndüren uç noktalar için."""
    out = subprocess.run(
        ["gh", "api", "--paginate", path, "--jq", ".[]"], check=True, capture_output=True
    ).stdout.decode("utf-8")
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def collect(repo: str) -> list[dict[str, Any]]:
    pulls = paged(f"repos/{repo}/pulls?state=all&per_page=100")
    by_sha = {p["head"]["sha"]: p["number"] for p in pulls}
    by_branch = {p["head"]["ref"]: p["number"] for p in pulls}  # PR'a sonradan commit eklenmişse
    artifacts = [
        a
        for page in [gh_json(f"repos/{repo}/actions/artifacts?per_page=100")]
        for a in page["artifacts"]
        if a["name"].startswith("aegis-runs-") and not a["expired"]
    ]
    rows: list[dict[str, Any]] = []
    for a in artifacts:
        run_id = a["workflow_run"]["id"]
        run = gh_json(f"repos/{repo}/actions/runs/{run_id}")
        linked = [p["number"] for p in run.get("pull_requests", [])]
        number = (
            linked[0] if linked else by_sha.get(run["head_sha"], by_branch.get(run["head_branch"]))
        )
        try:
            blob = gh(f"repos/{repo}/actions/artifacts/{a['id']}/zip")
        except subprocess.CalledProcessError:
            try:  # GitHub zaman zaman geçici hata verir; bir kez daha dene
                blob = gh(f"repos/{repo}/actions/artifacts/{a['id']}/zip")
            except subprocess.CalledProcessError:
                print(f"{repo}: artifact {a['id']} indirilemedi, atlandı", file=sys.stderr)
                continue
        archive = zipfile.ZipFile(io.BytesIO(blob))
        records = [
            json.loads(line)
            for name in archive.namelist()
            for line in archive.read(name).decode("utf-8").splitlines()
            if line.strip()
        ]
        if not records or number is None:
            continue
        record = records[-1]  # aynı çalıştırmada birden fazla kayıt olursa sonuncusu
        rows.append(
            {
                "repo": repo,
                "pr": number,
                "workflow_run": run_id,
                "head_sha": run["head_sha"],
                "created_at": a["created_at"],
                **{k: v for k, v in record.items() if k not in ("repo", "pr")},
            }
        )
        print(
            f"{repo}#{number}: {record.get('status')} risk={record.get('risk_band')}",
            file=sys.stderr,
        )
    # PR başına yorum geri bildirimi (yalnız bir kez sorulur).
    feedback: dict[int, dict[str, int]] = {}
    for number in sorted({r["pr"] for r in rows}):
        comments = paged(f"repos/{repo}/issues/{number}/comments?per_page=100")
        summary = next((c for c in reversed(comments) if MARKER in (c.get("body") or "")), None)
        reactions = summary.get("reactions", {}) if summary else {}
        inline = paged(f"repos/{repo}/pulls/{number}/comments?per_page=100")
        feedback[number] = {
            "summary_comment": summary is not None,
            "thumbs_up": reactions.get("+1", 0),
            "thumbs_down": reactions.get("-1", 0),
            "inline_comments": sum(1 for c in inline if c.get("user", {}).get("type") == "Bot"),
        }
    return [{**r, **feedback[r["pr"]]} for r in rows]


def cmd_collect() -> None:
    rows = [row for repo in REPOS for row in collect(repo)]
    rows.sort(key=lambda r: (r["repo"], r["pr"], r["created_at"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    prs = {(r["repo"], r["pr"]) for r in rows}
    print(f"{len(rows)} çalıştırma, {len(prs)} PR → {OUT}")


def main() -> None:
    if sys.argv[1:] == ["topla"]:
        cmd_collect()
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
