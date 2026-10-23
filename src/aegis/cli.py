"""Aegis komut satırı arayüzü."""

import io
import logging
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import typer
from rich.console import Console

from aegis import __version__
from aegis.config import load_config
from aegis.diff import filter_diff, git_commit_messages, git_diff, load_ignore_spec, parse_diff
from aegis.gatekeeper import HeuristicGatekeeper, RiskBand
from aegis.github.action import run_action
from aegis.llm import ResponseCache
from aegis.review import ReviewResult, ReviewStatus, run_review
from aegis.telemetry.runs import append_run

app = typer.Typer(
    help="Risk odaklı, hafızalı ve çok ajanlı PR inceleme sistemi.", no_args_is_help=True
)
# Windows konsolları (cp1254 vb.) bazı karakterleri yazamaz; çökmek yerine yerine koy.
for _stream in (sys.stdout, sys.stderr):
    if isinstance(_stream, io.TextIOWrapper):
        _stream.reconfigure(errors="replace")
console = Console()


def _not_implemented(phase: str) -> None:
    console.print(f"[yellow]Henüz uygulanmadı — {phase}.[/yellow]")


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"aegis {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Sürümü göster ve çık.",
    ),
) -> None:
    """Aegis CLI."""


@app.command()
def mine() -> None:
    """Repo geçmişini tarar, fix commit'lerini ve SZZ eşlemelerini çıkarır. (Faz 1)"""
    _not_implemented("Faz 1")


@app.command()
def train() -> None:
    """Gatekeeper risk modelini eğitir. (Faz 2)"""
    _not_implemented("Faz 2")


_BAND_STYLE = {RiskBand.LOW: "green", RiskBand.MEDIUM: "yellow", RiskBand.HIGH: "red"}


@app.command()
def score(
    base: str = typer.Option("main", "--base", help="Karşılaştırılacak taban dal/commit."),
    head: str = typer.Option("HEAD", "--head", help="İncelenecek dal/commit."),
    repo: Path = typer.Option(Path("."), "--repo", help="Git deposunun yolu."),
) -> None:
    """`base...head` aralığı için risk skoru hesaplar (şimdilik sezgisel kural)."""
    config = load_config(repo)
    try:
        text = git_diff(base, head, repo=repo)
    except subprocess.CalledProcessError as exc:
        console.print(f"[red]git diff başarısız:[/red] {exc.stderr.strip()}")
        raise typer.Exit(2) from exc
    filtered = filter_diff(
        parse_diff(text),
        ignore=load_ignore_spec(repo),
        max_changed_lines=config.filters.max_changed_lines_per_file,
    )
    result = HeuristicGatekeeper(config.gatekeeper).assess(filtered.diff, as_of=datetime.now(UTC))

    style = _BAND_STYLE[result.band]
    console.print(f"Risk: [bold {style}]{result.score:.2f} ({result.band})[/bold {style}]")
    for reason in result.reasons:
        console.print(f"  • {reason}")
    if filtered.skipped:
        skipped = ", ".join(f"{s.path} ({s.reason})" for s in filtered.skipped)
        console.print(f"[dim]Elenen dosyalar: {skipped}[/dim]")


@app.command()
def index() -> None:
    """Bug-fix hafızasını (hata kartları) oluşturur veya günceller. (Faz 3)"""
    _not_implemented("Faz 3")


_SEVERITY_STYLE = {"critical": "bold red", "high": "red", "medium": "yellow", "low": "dim"}


def _print_review(result: ReviewResult) -> None:
    if result.risk is not None:
        style = _BAND_STYLE[result.risk.band]
        console.print(
            f"Risk: [bold {style}]{result.risk.score:.2f} ({result.risk.band})[/bold {style}]"
        )
        for reason in result.risk.reasons:
            console.print(f"  • {reason}")
    status_note = {
        ReviewStatus.SKIPPED_LOW_RISK: "[green]Risk düşük, LLM çağrılmadı.[/green]",
        ReviewStatus.SKIPPED_NO_LLM: "[yellow]LLM devre dışı; yalnızca kurallar çalıştı.[/yellow]",
        ReviewStatus.LLM_ERROR: f"[yellow]LLM başarısız (fail-open): {result.error}[/yellow]",
        ReviewStatus.ERROR: f"[red]Aegis hatası (fail-open): {result.error}[/red]",
    }.get(result.status)
    if status_note:
        console.print(status_note)
    if result.summary:
        console.print(f"\n[bold]Özet:[/bold] {result.summary}")
    for warning in result.metadata_warnings:
        console.print(f"[red]⚠ PR metninde şüpheli talimat:[/red] {warning}")
    console.print(f"\n[bold]{len(result.findings)} bulgu[/bold]")
    for f in result.findings:
        style = _SEVERITY_STYLE.get(f.severity, "")
        lines = f"{f.line}-{f.end_line}" if f.end_line and f.end_line != f.line else f"{f.line}"
        console.print(
            f"[{style}]{f.severity}[/{style}] {f.file}:{lines} "
            f"[{f.category} · {f.confidence:.2f}] [bold]{f.title}[/bold]"
        )
        console.print(f"    {f.explanation}", highlight=False)
    details = [f"{result.files_reviewed} dosya"]
    if result.dropped:
        details.append(f"{len(result.dropped)} bulgu düşürüldü")
    if result.skipped_files:
        details.append(f"elenen: {', '.join(result.skipped_files)}")
    if result.omitted_files:
        details.append(f"boyut sınırı nedeniyle incelenmeyen: {', '.join(result.omitted_files)}")
    if result.provider:
        cache_note = " (cache)" if result.cached else ""
        details.append(
            f"{result.provider}/{result.model} · prompt {result.prompt_version} · "
            f"{result.usage.input_tokens}+{result.usage.output_tokens} token{cache_note}"
        )
    details.append(f"{result.duration_seconds:.1f} sn")
    console.print(f"[dim]{' · '.join(details)}[/dim]")


@app.command()
def review(
    base: str = typer.Option("main", "--base", help="Karşılaştırılacak taban dal/commit."),
    head: str = typer.Option("HEAD", "--head", help="İncelenecek dal/commit."),
    repo: Path = typer.Option(Path("."), "--repo", help="Git deposunun yolu."),
    config_path: Path | None = typer.Option(
        None, "--config", help="Yapılandırma dosyası (varsayılan: <repo>/.aegis.toml)."
    ),
    no_llm: bool = typer.Option(False, "--no-llm", help="LLM çağırma; yalnızca kurallar."),
    no_cache: bool = typer.Option(False, "--no-cache", help="LLM yanıt cache'ini kullanma."),
    json_out: Path | None = typer.Option(
        None, "--json-out", help="Sonucun tamamını JSON olarak bu dosyaya yaz."
    ),
) -> None:
    """Gatekeeper + analiz ajanı hattını yerelde çalıştırır (FR-44)."""
    config = load_config(repo, config_path)
    try:
        text = git_diff(base, head, repo=repo)
        metadata = git_commit_messages(base, head, repo=repo)
    except subprocess.CalledProcessError as exc:
        console.print(f"[red]git başarısız:[/red] {exc.stderr.strip()}")
        raise typer.Exit(2) from exc
    result = run_review(
        text,
        config,
        ignore=load_ignore_spec(repo),
        metadata=metadata,
        llm_enabled=not no_llm,
        cache=None if no_cache else ResponseCache(repo / config.review.cache_dir),
    )
    append_run(repo / config.review.runs_path, result, base=base, head=head, source="cli")
    _print_review(result)
    if json_out is not None:
        json_out.write_text(result.model_dump_json(indent=2), encoding="utf-8")


@app.command(name="github")
def github_action(
    repo: Path = typer.Option(Path("."), "--repo", help="Git deposunun yolu."),
    config_path: str = typer.Option(
        ".aegis.toml", "--config", help="Taban commit'te okunacak yapılandırma dosyası."
    ),
    json_out: Path | None = typer.Option(None, "--json-out", help="Sonucu JSON olarak yaz."),
) -> None:
    """GitHub Action içinde PR'ı inceler ve sonucu yayınlar (her zaman 0 ile çıkar)."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    raise typer.Exit(run_action(repo=repo, config_path=config_path, json_out=json_out))


@app.command(name="eval")
def eval_() -> None:
    """Değerlendirme deneylerini koşturur. (Faz 7)"""
    _not_implemented("Faz 7")
