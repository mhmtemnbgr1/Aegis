"""GitHub REST API'nin Aegis'in kullandığı küçük bir alt kümesi."""

from typing import Any

import httpx

API_URL = "https://api.github.com"
_PAGE_SIZE = 100


class GitHubError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class GitHubClient:
    def __init__(
        self,
        token: str,
        repository: str,
        *,
        api_url: str = API_URL,
        http: httpx.Client | None = None,
        timeout: float = 30,
    ) -> None:
        self.repository = repository
        self._http = http or httpx.Client(timeout=timeout)
        self._base = f"{api_url.rstrip('/')}/repos/{repository}"
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            resp = self._http.request(method, self._base + path, headers=self._headers, **kwargs)
        except httpx.HTTPError as exc:
            raise GitHubError(f"{method} {path}: {exc}") from exc
        if resp.status_code >= 400:
            raise GitHubError(
                f"{method} {path}: HTTP {resp.status_code} {resp.text[:300]}", resp.status_code
            )
        return resp.json() if resp.content else None

    def _paginate(self, path: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page = 1
        while True:
            batch = self._request("GET", path, params={"per_page": _PAGE_SIZE, "page": page})
            items.extend(batch)
            if len(batch) < _PAGE_SIZE:
                return items
            page += 1

    # Özet yorumu (issue yorumu)
    def list_issue_comments(self, number: int) -> list[dict[str, Any]]:
        return self._paginate(f"/issues/{number}/comments")

    def create_issue_comment(self, number: int, body: str) -> dict[str, Any]:
        result: dict[str, Any] = self._request(
            "POST", f"/issues/{number}/comments", json={"body": body}
        )
        return result

    def update_issue_comment(self, comment_id: int, body: str) -> None:
        self._request("PATCH", f"/issues/comments/{comment_id}", json={"body": body})

    # Satır yorumları (review yorumları)
    def list_review_comments(self, number: int) -> list[dict[str, Any]]:
        return self._paginate(f"/pulls/{number}/comments")

    def create_review(
        self, number: int, commit_sha: str, comments: list[dict[str, Any]], body: str = ""
    ) -> None:
        payload: dict[str, Any] = {
            "commit_id": commit_sha,
            "event": "COMMENT",
            "comments": comments,
        }
        if body:
            payload["body"] = body
        self._request("POST", f"/pulls/{number}/reviews", json=payload)

    def create_review_comment(self, number: int, commit_sha: str, comment: dict[str, Any]) -> None:
        self._request(
            "POST", f"/pulls/{number}/comments", json={"commit_id": commit_sha, **comment}
        )

    def update_review_comment(self, comment_id: int, body: str) -> None:
        self._request("PATCH", f"/pulls/comments/{comment_id}", json={"body": body})

    # Issue etiketleri (fix-commit tespiti)
    def get_issue_labels(self, number: int) -> list[str] | None:
        """Issue veya PR'ın etiket adları; bulunamazsa (404/410) None."""
        try:
            issue = self._request("GET", f"/issues/{number}")
        except GitHubError as exc:
            if exc.status_code in (404, 410):
                return None
            raise
        return [str(label["name"]) for label in issue.get("labels", [])]

    def get_issue(self, number: int) -> dict[str, Any] | None:
        """Issue veya PR'ın etiketleri, açılış zamanı ve PR olup olmadığı; bulunamazsa None."""
        try:
            issue = self._request("GET", f"/issues/{number}")
        except GitHubError as exc:
            if exc.status_code in (404, 410):
                return None
            raise
        return {
            "labels": [str(label["name"]) for label in issue.get("labels", [])],
            "created_at": issue.get("created_at"),
            "pull": "pull_request" in issue,
        }

    def get_issue_title(self, number: int) -> str | None:
        """Issue veya PR'ın başlığı; bulunamazsa (404/410) None (hata kartları, #22)."""
        try:
            issue = self._request("GET", f"/issues/{number}")
        except GitHubError as exc:
            if exc.status_code in (404, 410):
                return None
            raise
        title = issue.get("title")
        return str(title) if title else None

    # Release asset'leri (durum arşivi, #45)
    def get_release_by_tag(self, tag: str) -> dict[str, Any] | None:
        try:
            release: dict[str, Any] = self._request("GET", f"/releases/tags/{tag}")
        except GitHubError as exc:
            if exc.status_code == 404:
                return None
            raise
        return release

    def create_release(self, tag: str, *, name: str, body: str) -> dict[str, Any]:
        release: dict[str, Any] = self._request(
            "POST", "/releases", json={"tag_name": tag, "name": name, "body": body}
        )
        return release

    def delete_release_asset(self, asset_id: int) -> None:
        self._request("DELETE", f"/releases/assets/{asset_id}")

    def upload_release_asset(
        self, release: dict[str, Any], name: str, data: bytes
    ) -> dict[str, Any]:
        # Yükleme ayrı bir sunucuya gider: release'in `upload_url` şablonu ({?name,label}).
        url = str(release["upload_url"]).split("{", 1)[0]
        try:
            resp = self._http.post(
                url,
                params={"name": name},
                content=data,
                headers={**self._headers, "Content-Type": "application/gzip"},
            )
        except httpx.HTTPError as exc:
            raise GitHubError(f"POST {url}: {exc}") from exc
        if resp.status_code >= 400:
            raise GitHubError(
                f"POST {url}: HTTP {resp.status_code} {resp.text[:300]}", resp.status_code
            )
        result: dict[str, Any] = resp.json()
        return result

    def download_release_asset(self, asset_id: int) -> bytes:
        try:
            resp = self._http.get(
                f"{self._base}/releases/assets/{asset_id}",
                headers={**self._headers, "Accept": "application/octet-stream"},
                follow_redirects=True,
            )
        except httpx.HTTPError as exc:
            raise GitHubError(f"GET asset {asset_id}: {exc}") from exc
        if resp.status_code >= 400:
            raise GitHubError(f"GET asset {asset_id}: HTTP {resp.status_code}", resp.status_code)
        return resp.content

    # Check run
    def create_check_run(
        self, head_sha: str, *, name: str, conclusion: str, title: str, summary: str
    ) -> None:
        self._request(
            "POST",
            "/check-runs",
            json={
                "name": name,
                "head_sha": head_sha,
                "status": "completed",
                "conclusion": conclusion,
                "output": {"title": title, "summary": summary[:65000]},
            },
        )
