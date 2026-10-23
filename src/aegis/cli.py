"""Aegis komut satırı arayüzü."""

import typer
from rich.console import Console

from aegis import __version__

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


@app.command()
def score() -> None:
    """Bir commit aralığı için risk skoru hesaplar. (Faz 2)"""
    _not_implemented("Faz 2")


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
