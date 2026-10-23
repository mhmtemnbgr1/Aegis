"""Testler için bellek içi sahte GitHub REST sunucusu (httpx.MockTransport)."""

import json
import re
from typing import Any

import httpx

from aegis.github.client import GitHubClient

REPO = "owner/repo"


class FakeGitHub:
    def __init__(self) -> None:
        self.issue_comments: list[dict[str, Any]] = []
        self.review_comments: list[dict[str, Any]] = []
        self.check_runs: list[dict[str, Any]] = []
        self.requests: list[tuple[str, str]] = []
        self.fail: dict[str, int] = {}
        """Yol kalıbı → döndürülecek HTTP hata kodu."""
        self.invalid_lines: set[tuple[str, int]] = set()
        """Review'da bu (dosya, satır) varsa 422 döner (diff dışı satır)."""
        self._next_id = 1

    def client(self) -> GitHubClient:
        return GitHubClient(
            "test-token", REPO, http=httpx.Client(transport=httpx.MockTransport(self._handle))
        )

    def _id(self) -> int:
        self._next_id += 1
        return self._next_id

    def _handle(self, request: httpx.Request) -> httpx.Response:
        method, path = request.method, request.url.path.removeprefix(f"/repos/{REPO}")
        self.requests.append((method, path))
        assert request.headers["Authorization"] == "Bearer test-token"
        for pattern, status in self.fail.items():
            if re.fullmatch(pattern, f"{method} {path}"):
                return httpx.Response(status, json={"message": "boom"})
        body = json.loads(request.content) if request.content else {}
        page = int(request.url.params.get("page", 1))
        per_page = int(request.url.params.get("per_page", 30))

        def paged(items: list[dict[str, Any]]) -> httpx.Response:
            return httpx.Response(200, json=items[(page - 1) * per_page : page * per_page])

        if re.fullmatch(r"/issues/\d+/comments", path):
            if method == "GET":
                return paged(self.issue_comments)
            comment = {"id": self._id(), "body": body["body"]}
            self.issue_comments.append(comment)
            return httpx.Response(201, json=comment)
        if m := re.fullmatch(r"/issues/comments/(\d+)", path):
            next(c for c in self.issue_comments if c["id"] == int(m[1]))["body"] = body["body"]
            return httpx.Response(200, json={})
        if re.fullmatch(r"/pulls/\d+/comments", path):
            if method == "GET":
                return paged(self.review_comments)
            if (body["path"], body["line"]) in self.invalid_lines:
                return httpx.Response(422, json={"message": "line not in diff"})
            self.review_comments.append({"id": self._id(), **body})
            return httpx.Response(201, json={})
        if re.fullmatch(r"/pulls/\d+/reviews", path):
            comments = body["comments"]
            if any((c["path"], c["line"]) in self.invalid_lines for c in comments):
                return httpx.Response(422, json={"message": "line not in diff"})
            for c in comments:
                self.review_comments.append({"id": self._id(), "commit_id": body["commit_id"], **c})
            return httpx.Response(200, json={})
        if m := re.fullmatch(r"/pulls/comments/(\d+)", path):
            next(c for c in self.review_comments if c["id"] == int(m[1]))["body"] = body["body"]
            return httpx.Response(200, json={})
        if path == "/check-runs":
            self.check_runs.append(body)
            return httpx.Response(201, json={})
        return httpx.Response(404, json={"message": f"{method} {path}"})
