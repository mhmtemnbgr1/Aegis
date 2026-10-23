"""Aegis komut satırı arayüzü."""

import subprocess
from datetime import UTC, datetime
from pathlib import Path

import typer
from rich.console import Console

from aegis import __version__
from aegis.config import load_config
from aegis.diff import filter_diff, git_diff, load_ignore_spec, parse_diff
from aegis.gatekeeper import HeuristicGatekeeper, RiskBand

app = typer.Typer(
    help="Risk odaklı, hafızalı ve çok ajanlı PR inceleme sistemi.", no_args_is_help=True
)
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


@app.command()
def review() -> None:
    """Gatekeeper + hafıza + ajan hattını çalıştırır. (Faz 4–6)"""
    _not_implemented("Faz 4")


@app.command(name="eval")
def eval_() -> None:
    """Değerlendirme deneylerini koşturur. (Faz 7)"""
    _not_implemented("Faz 7")
