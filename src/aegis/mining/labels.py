"""Bağlı issue etiketlerinin GitHub'dan okunması; sonuçlar diskte cache'lenir."""

import json
import logging
from collections.abc import Callable, Collection, Mapping
from pathlib import Path
from typing import Any

from aegis.github.client import GitHubClient

logger = logging.getLogger(__name__)


def github_label_source(
    client: GitHubClient,
    cache_path: Path,
    *,
    on_fetch: Callable[[int, int], None] | None = None,
) -> Callable[[Collection[int]], Mapping[int, Collection[str]]]:
    """Önce `cache_path` (JSON) okunur, eksik numaralar API'den çekilip cache'e eklenir.

    Bulunamayan issue'lar boş etiket listesiyle cache'lenir ve tekrar sorulmaz.
    `on_fetch(i, toplam)` ilerleme bildirimi içindir.
    """

    def source(numbers: Collection[int]) -> Mapping[int, Collection[str]]:
        cache: dict[str, list[str]] = {}
        if cache_path.is_file():
            cache = json.loads(cache_path.read_text("utf-8"))
        missing = [n for n in numbers if str(n) not in cache]
        try:
            for i, number in enumerate(missing, 1):
                cache[str(number)] = client.get_issue_labels(number) or []
                if on_fetch is not None:
                    on_fetch(i, len(missing))
        finally:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(cache, indent=0, sort_keys=True), "utf-8")
        return {n: cache.get(str(n), []) for n in numbers}

    return source


def github_issue_titles(
    client: GitHubClient, cache_path: Path
) -> Callable[[Collection[int]], Mapping[int, str | None]]:
    """Issue başlıkları (#22); `github_label_source` gibi diskte cache'lenir."""

    def source(numbers: Collection[int]) -> Mapping[int, str | None]:
        cache: dict[str, str | None] = {}
        if cache_path.is_file():
            cache = json.loads(cache_path.read_text("utf-8"))
        try:
            for number in (n for n in numbers if str(n) not in cache):
                cache[str(number)] = client.get_issue_title(number)
        finally:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(cache, indent=0, sort_keys=True), "utf-8")
        return {n: cache.get(str(n)) for n in numbers}

    return source


def github_issue_info(
    client: GitHubClient,
    cache_path: Path,
    *,
    on_fetch: Callable[[int, int], None] | None = None,
) -> Callable[[Collection[int]], Mapping[int, dict[str, Any] | None]]:
    """Issue/PR bilgisi (etiketler, açılış zamanı, PR mi); `github_label_source` gibi cache'lenir.

    SZZ süzgeçleri için (bkz. `aegis.mining.szz`): yalnızca hata etiketli issue'lara bağlı fix'ler
    ve hatanın bildirildiği zamandan önceki hata getiren commit'ler. Bulunamayan numaralar `None`.
    """

    def source(numbers: Collection[int]) -> Mapping[int, dict[str, Any] | None]:
        cache: dict[str, dict[str, Any] | None] = {}
        if cache_path.is_file():
            cache = json.loads(cache_path.read_text("utf-8"))
        missing = [n for n in numbers if str(n) not in cache]
        try:
            for i, number in enumerate(missing, 1):
                cache[str(number)] = client.get_issue(number)
                if on_fetch is not None:
                    on_fetch(i, len(missing))
        finally:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(cache, indent=0, sort_keys=True), "utf-8")
        return {n: cache.get(str(n)) for n in numbers}

    return source
