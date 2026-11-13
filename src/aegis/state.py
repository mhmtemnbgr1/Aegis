"""Durum arşivi: madencilik verisi, modeller ve hafıza tek dosyada (FR-07, #45).

Tüm geçmişi CI'da taramak büyük repolarda çok uzun sürer. İlk madencilik, eğitim ve indeksleme
yerelde yapılır; `aegis publish-state` sonucu tek bir `tar.gz` arşivinde toplar ve repo'nun bir
GitHub Release'ine (`[state].release_tag`) asset olarak yükler. Action önce `actions/cache`'e, yoksa
Release asset'ine bakar (`aegis fetch-state`); ikisi de yoksa sezgisel gatekeeper ile hafızasız
çalışır (fail-open). Hiçbir durumda geçmiş yeniden taranmaz.

Arşiv içeriği (`.aegis/` altındaki yerleşimle aynı, köke göre göreli):

- `data/<repo>/`: commit, dosya, fonksiyon, Kamei, SZZ çıktıları, `meta.json`, `cards.jsonl`,
- `models/<repo>/` ve `models/all/`: yalnızca çalışma anında kullanılan model dosyası
  (`<model_name>-none.pkl`; repo modeli ve soğuk başlangıç için genel model). Deneylerden kalan
  diğer model varyantları arşive girmez,
- `memory/<repo>/`: vektör indeksi. Varsayılan LSA indeksi kartlardan türetildiği ve birkaç
  saniyede yeniden kurulduğu için arşive girmez; `aegis fetch-state` kartlardan yeniden kurar.
  Yeniden kurulamayan embedding'lerde (ör. `ollama:<model>`) indeks arşivdedir,
- `state.json`: sürüm kaydı (şema, Aegis sürümü, repo, işlenen son SHA, oluşturma zamanı, dosyalar).
"""

import io
import json
import tarfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from aegis import __version__

SCHEMA_VERSION = 1
MANIFEST = "state.json"


@dataclass(frozen=True)
class StatePaths:
    """Durumun yerel dizinleri (config'den: `[mining].data_dir`, `[gatekeeper].models_dir`,
    `[memory].index_path`)."""

    data: Path
    models: Path
    memory: Path

    def sections(self, slug: str, *, include_memory: bool = True) -> dict[str, Path]:
        out = {
            f"data/{slug}": self.data / slug,
            f"models/{slug}": self.models / slug,
            "models/all": self.models / "all",
        }
        if include_memory:
            out[f"memory/{slug}"] = self.memory / slug
        return out


def asset_name(slug: str) -> str:
    return f"aegis-state-{slug}.tar.gz"


def pack_state(
    slug: str, paths: StatePaths, *, model_name: str = "lr", include_memory: bool = True
) -> tuple[bytes, dict[str, Any]]:
    """Arşivin baytları ve sürüm kaydı. Olmayan bölümler atlanır; veri dizini zorunludur."""
    sections = paths.sections(slug, include_memory=include_memory)
    model_file = f"{model_name}-none.pkl"
    if not sections[f"data/{slug}"].is_dir():
        raise FileNotFoundError(f"{paths.data / slug} yok; önce aegis mine")
    files: list[str] = []
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for prefix, directory in sections.items():
            if not directory.is_dir():
                continue
            for path in sorted(p for p in directory.rglob("*") if p.is_file()):
                if prefix.startswith("models/") and path.name != model_file:
                    continue
                name = f"{prefix}/{path.relative_to(directory).as_posix()}"
                tar.add(path, arcname=name)
                files.append(name)
        meta_path = paths.data / slug / "meta.json"
        meta = json.loads(meta_path.read_text("utf-8")) if meta_path.is_file() else {}
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "aegis_version": __version__,
            "repo": slug,
            "head_sha": meta.get("head_sha"),
            "created_at": datetime.now(UTC).isoformat(),
            "model": model_file,
            "memory_included": include_memory,
            "files": files,
        }
        data = json.dumps(manifest, indent=1).encode("utf-8")
        info = tarfile.TarInfo(MANIFEST)
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    return buffer.getvalue(), manifest


def unpack_state(archive: bytes, paths: StatePaths) -> dict[str, Any]:
    """Arşivi yerel dizinlere açar; sürüm kaydını döndürür.

    Yalnızca bilinen bölümlere (`data/`, `models/`, `memory/`) düz dosya yazılır; mutlak yollar,
    `..` içeren adlar, bağlantılar ve bilinmeyen bölümler reddedilir.
    """
    roots = {"data": paths.data, "models": paths.models, "memory": paths.memory}
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        manifest_member = tar.getmember(MANIFEST)
        handle = tar.extractfile(manifest_member)
        if handle is None:
            raise ValueError("arşivde sürüm kaydı okunamadı")
        manifest: dict[str, Any] = json.loads(handle.read().decode("utf-8"))
        if manifest.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("desteklenmeyen durum arşivi sürümü")
        for member in tar.getmembers():
            if member.name == MANIFEST:
                continue
            name = PurePosixPath(member.name)
            if not member.isfile() or name.is_absolute() or ".." in name.parts:
                raise ValueError(f"güvensiz arşiv girdisi: {member.name}")
            if name.parts[0] not in roots or len(name.parts) < 3:
                raise ValueError(f"bilinmeyen arşiv bölümü: {member.name}")
            target = roots[name.parts[0]].joinpath(*name.parts[1:])
            target.parent.mkdir(parents=True, exist_ok=True)
            source = tar.extractfile(member)
            if source is None:
                raise ValueError(f"okunamayan arşiv girdisi: {member.name}")
            target.write_bytes(source.read())
    return manifest


def publish_state(client: Any, tag: str, slug: str, archive: bytes) -> str:
    """Arşivi `tag` etiketli Release'e yükler (yoksa oluşturur, aynı adlı eski asset'i siler).

    Asset'in indirme adresini döndürür.
    """
    release = client.get_release_by_tag(tag)
    if release is None:
        release = client.create_release(
            tag,
            name="Aegis state",
            body="Aegis durum arşivleri (aegis publish-state). Elle düzenlemeyin.",
        )
    name = asset_name(slug)
    for asset in release.get("assets", []):
        if asset["name"] == name:
            client.delete_release_asset(asset["id"])
    uploaded = client.upload_release_asset(release, name, archive)
    return str(uploaded.get("browser_download_url", ""))


def fetch_state(client: Any, tag: str, slug: str, paths: StatePaths) -> dict[str, Any] | None:
    """Release asset'ini indirip açar; Release ya da asset yoksa None."""
    release = client.get_release_by_tag(tag)
    if release is None:
        return None
    asset = next((a for a in release.get("assets", []) if a["name"] == asset_name(slug)), None)
    if asset is None:
        return None
    return unpack_state(client.download_release_asset(asset["id"]), paths)
