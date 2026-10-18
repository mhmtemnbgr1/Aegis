"""Aegis komut satırı arayüzü."""

import typer
from rich.console import Console

from aegis import __version__

app = typer.Typer(help="LLM destekli pre-push kod inceleme aracı.", no_args_is_help=True)
console = Console()


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"aegis {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", "-V", callback=_version_callback, is_eager=True,
        help="Sürümü göster ve çık.",
    ),
) -> None:
    """Aegis CLI."""


@app.command()
def install() -> None:
    """Mevcut depoya pre-push hook'unu kurar. (Faz 1)"""
    console.print("[yellow]Henüz uygulanmadı — Faz 1.[/yellow]")


@app.command()
def review() -> None:
    """Hook olmadan manuel inceleme yapar. (Faz 1)"""
    console.print("[yellow]Henüz uygulanmadı — Faz 1.[/yellow]")
