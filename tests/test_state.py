"""Durum arşivi: paketleme, güvenli açma, Release yükleme/indirme (#45)."""

import io
import json
import tarfile
from pathlib import Path
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from aegis.cli import app
from aegis.github.client import GitHubClient
from aegis.state import (
    MANIFEST,
    StatePaths,
    asset_name,
    fetch_state,
    pack_state,
    publish_state,
    unpack_state,
)


def _paths(root: Path) -> StatePaths:
    return StatePaths(data=root / "data", models=root / "models", memory=root / "memory")


def _populate(root: Path, slug: str = "o__r") -> StatePaths:
    paths = _paths(root)
    (paths.data / slug).mkdir(parents=True)
    (paths.data / slug / "commits.parquet").write_bytes(b"PAR1")
    (paths.data / slug / "meta.json").write_text('{"head_sha": "abc123"}', "utf-8")
    (paths.data / slug / "cards.jsonl").write_text("{}\n", "utf-8")
    (paths.models / slug).mkdir(parents=True)
    (paths.models / slug / "lr-none.pkl").write_bytes(b"model")
    (paths.models / "all").mkdir()
    (paths.models / "all" / "lr-none.pkl").write_bytes(b"general")
    (paths.models / "other__repo").mkdir()
    (paths.models / "other__repo" / "lr-none.pkl").write_bytes(b"x")  # başka repo: arşive girmez
    (paths.memory / slug).mkdir(parents=True)
    (paths.memory / slug / "vectors.npy").write_bytes(b"npy")
    return paths


def test_pack_unpack_roundtrip(tmp_path: Path) -> None:
    archive, manifest = pack_state("o__r", _populate(tmp_path / "src"))
    assert manifest["repo"] == "o__r" and manifest["head_sha"] == "abc123"
    assert "models/all/lr-none.pkl" in manifest["files"]
    assert not any("other__repo" in f for f in manifest["files"])
    target = _paths(tmp_path / "dst")
    assert unpack_state(archive, target)["files"] == manifest["files"]
    assert (target.data / "o__r" / "commits.parquet").read_bytes() == b"PAR1"
    assert (target.models / "all" / "lr-none.pkl").read_bytes() == b"general"
    assert (target.memory / "o__r" / "vectors.npy").read_bytes() == b"npy"
    with pytest.raises(FileNotFoundError):
        pack_state("yok", _paths(tmp_path / "src"))


def _tar(entries: dict[str, bytes], manifest: dict[str, Any] | None = None) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for name, data in {
            MANIFEST: json.dumps(manifest or {"schema_version": 1}).encode(),
            **entries,
        }.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


@pytest.mark.parametrize("name", ["data/../../evil.txt", "/etc/passwd", "secrets/o__r/x", "data/x"])
def test_unsafe_entries_are_rejected(tmp_path: Path, name: str) -> None:
    with pytest.raises(ValueError):
        unpack_state(_tar({name: b"x"}), _paths(tmp_path))
    assert not (tmp_path.parent / "evil.txt").exists()


def test_wrong_schema_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="sürümü"):
        unpack_state(_tar({}, {"schema_version": 99}), _paths(tmp_path))


class FakeClient:
    def __init__(self) -> None:
        self.release: dict[str, Any] | None = None
        self.blobs: dict[int, bytes] = {}
        self.deleted: list[int] = []

    def get_release_by_tag(self, tag: str) -> dict[str, Any] | None:
        return self.release

    def create_release(self, tag: str, *, name: str, body: str) -> dict[str, Any]:
        self.release = {"tag_name": tag, "assets": [], "upload_url": "u{?name}"}
        return self.release

    def delete_release_asset(self, asset_id: int) -> None:
        self.deleted.append(asset_id)
        assert self.release is not None
        self.release["assets"] = [a for a in self.release["assets"] if a["id"] != asset_id]

    def upload_release_asset(
        self, release: dict[str, Any], name: str, data: bytes
    ) -> dict[str, Any]:
        asset_id = len(self.blobs) + 1
        self.blobs[asset_id] = data
        release["assets"].append({"id": asset_id, "name": name})
        return {"browser_download_url": f"https://example.invalid/{name}"}

    def download_release_asset(self, asset_id: int) -> bytes:
        return self.blobs[asset_id]


def test_publish_and_fetch(tmp_path: Path) -> None:
    client = FakeClient()
    target = _paths(tmp_path / "dst")
    assert fetch_state(client, "aegis-state", "o__r", target) is None  # Release yok
    archive, _ = pack_state("o__r", _populate(tmp_path / "src"))
    url = publish_state(client, "aegis-state", "o__r", archive)
    assert url.endswith(asset_name("o__r"))
    publish_state(client, "aegis-state", "o__r", archive)  # ikinci yükleme eskisini değiştirir
    assert client.deleted == [1]
    assert fetch_state(client, "aegis-state", "o__r", target) is not None
    assert (target.models / "o__r" / "lr-none.pkl").read_bytes() == b"model"
    assert fetch_state(client, "aegis-state", "baska__repo", target) is None


def test_client_release_endpoints() -> None:
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, str(request.url)))
        if request.url.path.endswith("/releases/tags/aegis-state"):
            return httpx.Response(404, json={})
        if request.url.host == "uploads.github.com":
            assert request.url.params["name"] == "a.tar.gz" and request.content == b"data"
            return httpx.Response(201, json={"browser_download_url": "d"})
        if request.url.path.endswith("/releases/assets/7"):
            return httpx.Response(200, content=b"blob")
        return httpx.Response(201, json={"id": 1})

    client = GitHubClient("t", "o/r", http=httpx.Client(transport=httpx.MockTransport(handler)))
    assert client.get_release_by_tag("aegis-state") is None
    release = {"upload_url": "https://uploads.github.com/repos/o/r/releases/1/assets{?name,label}"}
    assert client.upload_release_asset(release, "a.tar.gz", b"data") == {
        "browser_download_url": "d"
    }
    assert client.download_release_asset(7) == b"blob"


def test_cli_state_commands(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.gitrepo import GitRepo

    (tmp_path / "repo").mkdir()
    git = GitRepo(tmp_path / "repo")
    git.commit("init", {"a.py": "x = 1\n"})
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    _populate(tmp_path / ".aegis", slug="repo")
    runner = CliRunner()
    out = tmp_path / "state.tar.gz"
    result = runner.invoke(app, ["publish-state", str(git.path), "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert out.is_file() and "Arşiv:" in result.output
    no_token = runner.invoke(app, ["publish-state", str(git.path)])
    assert no_token.exit_code == 2
    fetched = runner.invoke(app, ["fetch-state", str(git.path)])
    assert fetched.exit_code == 0 and "GITHUB_TOKEN yok" in fetched.output
    skipped = runner.invoke(app, ["fetch-state", str(git.path), "--if-missing"])
    assert skipped.exit_code == 0 and "zaten var" in skipped.output


def test_pack_as_another_repo(tmp_path: Path) -> None:
    archive, manifest = pack_state("o__r", _populate(tmp_path / "src"), target="me__r")
    assert manifest["repo"] == "me__r" and manifest["source_repo"] == "o__r"
    assert "data/me__r/commits.parquet" in manifest["files"]
    assert "models/all/lr-none.pkl" in manifest["files"]
    target = _paths(tmp_path / "dst")
    unpack_state(archive, target)
    assert (target.data / "me__r" / "cards.jsonl").is_file()


def test_archive_keeps_only_runtime_model_and_can_skip_memory(tmp_path: Path) -> None:
    paths = _populate(tmp_path / "src")
    (paths.models / "o__r" / "rf-smote.pkl").write_bytes(b"deney")  # deney varyantı
    _, manifest = pack_state("o__r", paths, model_name="lr", include_memory=False)
    assert manifest["model"] == "lr-none.pkl" and manifest["memory_included"] is False
    assert not any(f.endswith("rf-smote.pkl") for f in manifest["files"])
    assert not any(f.startswith("memory/") for f in manifest["files"])
    assert "models/o__r/lr-none.pkl" in manifest["files"]


def test_client_get_issue() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/issues/9"):
            return httpx.Response(404, json={})
        return httpx.Response(
            200,
            json={
                "labels": [{"name": "bug"}],
                "created_at": "2024-01-01T00:00:00Z",
                "pull_request": {"url": "u"},
            },
        )

    client = GitHubClient("t", "o/r", http=httpx.Client(transport=httpx.MockTransport(handler)))
    assert client.get_issue(5) == {
        "labels": ["bug"],
        "created_at": "2024-01-01T00:00:00Z",
        "pull": True,
    }
    assert client.get_issue(9) is None
