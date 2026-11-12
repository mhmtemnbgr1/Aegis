"""Geçmişi bilinen geçici git depoları oluşturmak için yardımcı (madencilik testleri)."""

import os
import subprocess
from pathlib import Path


class GitRepo:
    def __init__(self, path: Path, branch: str = "main") -> None:
        self.path = path
        self.run("init", "-q", "-b", branch)
        self.run("config", "user.email", "dev@example.com")
        self.run("config", "user.name", "Dev")
        self.run("config", "commit.gpgsign", "false")
        self.run("config", "core.autocrlf", "false")

    def run(self, *args: str, env: dict[str, str] | None = None) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=self.path,
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, **env} if env else None,
        )
        return result.stdout.strip()

    def commit(
        self,
        message: str,
        files: dict[str, str | None],
        *,
        date: str = "2024-01-01T12:00:00+00:00",
        author: tuple[str, str] = ("Dev", "dev@example.com"),
    ) -> str:
        """`files`: yol → içerik (None ise dosya silinir). Commit'in SHA'sını döndürür."""
        for name, content in files.items():
            target = self.path / name
            if content is None:
                self.run("rm", "-q", name)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")
            self.run("add", name)
        env = {
            "GIT_AUTHOR_DATE": date,
            "GIT_COMMITTER_DATE": date,
            "GIT_AUTHOR_NAME": author[0],
            "GIT_AUTHOR_EMAIL": author[1],
        }
        self.run("commit", "-q", "--allow-empty", "-m", message, env=env)
        return self.run("rev-parse", "HEAD")
