"""Aegis komut satırı arayüzü."""

import io
import json
import logging
import math
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import polars as pl
import typer
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn
from rich.table import Table

from aegis import __version__
from aegis.config import load_config
from aegis.diff import filter_diff, git_commit_messages, git_diff, load_ignore_spec, parse_diff
from aegis.features import compute_kamei
from aegis.gatekeeper import HeuristicGatekeeper, RiskBand
from aegis.github.action import run_action
from aegis.github.client import GitHubClient
from aegis.llm import ResponseCache
from aegis.mining import (
    ensure_clone,
    github_repository,
    is_remote,
    mine_repository,
    repo_slug,
    slug_from_url,
)
from aegis.mining.dataset import build_d1
from aegis.mining.labels import github_label_source
from aegis.mining.miner import count_commits, remote_url
from aegis.mining.szz import run_szz
from aegis.review import ReviewResult, ReviewStatus, run_review
from aegis.telemetry.runs import append_run

app = typer.Typer(
    help="Risk odaklı, hafızalı ve çok ajanlı PR inceleme sistemi.", no_args_is_help=True
)
# Windows konsolları (cp1254 vb.) bazı karakterleri yazamaz; çökmek yerine yerine koy.
for _stream in (sys.stdout, sys.stderr):
    if isinstance(_stream, io.TextIOWrapper):
        _stream.reconfigure(errors="replace")
if TYPE_CHECKING:
    from aegis.gatekeeper.factory import ModelGatekeeper

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
def mine(
    repo: str = typer.Argument(..., help="Yerel git deposunun yolu veya klonlanacak URL."),
    out: Path | None = typer.Option(
        None, "--out", help="Çıktı kök dizini (varsayılan: [mining].data_dir)."
    ),
    config_path: Path | None = typer.Option(
        None, "--config", help="Yapılandırma dosyası (varsayılan: ./.aegis.toml)."
    ),
    since: datetime | None = typer.Option(
        None, "--since", help="Yalnızca bu tarihten sonraki commit'ler (YYYY-MM-DD)."
    ),
    no_functions: bool = typer.Option(
        False, "--no-functions", help="Fonksiyon düzeyindeki değişiklikleri çıkarma (daha hızlı)."
    ),
    issue_labels: bool = typer.Option(
        False,
        "--issue-labels",
        help="Bağlı issue etiketlerini GitHub'dan oku (GITHUB_TOKEN gerekir).",
    ),
    no_szz: bool = typer.Option(False, "--no-szz", help="SZZ eşlemesini çalıştırma."),
    szz_only: bool = typer.Option(
        False, "--szz-only", help="Taramayı atla; mevcut çıktı üzerinde yalnızca SZZ çalıştır."
    ),
    szz_variant: str | None = typer.Option(
        None, "--szz-variant", help="SZZ varyantı: ma veya b (varsayılan: [mining].szz_variant)."
    ),
) -> None:
    """Commit geçmişini tarar, fix commit'lerini bulur ve SZZ ile hatayı getiren commit'leri
    eşler. Çıktılar Parquet'e yazılır (docs/mining-schema.md)."""
    config = load_config(Path("."), config_path).mining
    if szz_variant is not None:
        if szz_variant not in ("ma", "b"):
            console.print("[red]--szz-variant ma veya b olmalı.[/red]")
            raise typer.Exit(2)
        config = config.model_copy(update={"szz_variant": szz_variant})
    if since is not None and since.tzinfo is None:
        since = since.replace(tzinfo=UTC)
    try:
        if is_remote(repo):
            console.print(f"Klonlanıyor: {repo}")
            path = ensure_clone(repo, Path(config.clone_dir))
            slug = slug_from_url(repo)
        else:
            path = Path(repo)
            slug = repo_slug(path)
        total = count_commits(path, since)
    except subprocess.CalledProcessError as exc:
        console.print(f"[red]git başarısız:[/red] {(exc.stderr or '').strip()}")
        raise typer.Exit(2) from exc

    out_dir = (out or Path(config.data_dir)) / slug
    label_source = None
    if issue_labels:
        url = remote_url(path)
        gh_repo = github_repository(url) if url else None
        token = os.environ.get("GITHUB_TOKEN")
        if gh_repo is None or not token:
            console.print("[red]--issue-labels için GitHub reposu ve GITHUB_TOKEN gerekir.[/red]")
            raise typer.Exit(2)
        label_source = github_label_source(
            GitHubClient(token, gh_repo), out_dir / "issue_labels.json"
        )

    def progress_bar() -> Progress:
        return Progress(
            TextColumn("{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=console,
        )

    if szz_only:
        if not (out_dir / "commits.parquet").is_file():
            console.print(f"[red]{out_dir} altında tarama çıktısı yok; önce aegis mine.[/red]")
            raise typer.Exit(2)
        # Fix kalıpları değişmiş olabilir: kararlar SZZ'den önce güncel kurallarla yenilenir.
        from aegis.mining.miner import reclassify

        before, after = reclassify(out_dir, config)
        console.print(f"Fix kararları yenilendi: {before} → {after}")
    else:
        with progress_bar() as progress:
            task = progress.add_task(f"{slug} taranıyor", total=total)
            result = mine_repository(
                path,
                out_dir,
                config,
                slug=slug,
                since=since,
                functions=not no_functions,
                label_source=label_source,
                on_commit=lambda: progress.advance(task),
            )
        console.print(
            f"[bold]{result.commits}[/bold] commit ({result.merges} merge, "
            f"[bold]{result.fixes}[/bold] fix) · {result.files} dosya değişikliği · "
            f"{result.functions} fonksiyon değişikliği · {result.duration_seconds:.1f} sn"
        )
        if result.function_errors:
            console.print(
                f"[yellow]{result.function_errors} dosyada fonksiyonlar çıkarılamadı.[/yellow]"
            )
        started = time.perf_counter()
        features = compute_kamei(
            pl.read_parquet(out_dir / "commits.parquet"), pl.read_parquet(out_dir / "files.parquet")
        )
        features.write_parquet(out_dir / "kamei.parquet")
        console.print(
            f"Kamei metrikleri: {features.height} commit · {time.perf_counter() - started:.1f} sn"
        )

    if not no_szz:
        with progress_bar() as progress:
            szz_task = progress.add_task(f"SZZ ({config.szz_variant})", total=None)
            try:
                szz = run_szz(
                    path,
                    out_dir,
                    config,
                    on_start=lambda n: progress.update(szz_task, total=n),
                    on_fix=lambda: progress.advance(szz_task),
                )
            except subprocess.CalledProcessError as exc:
                console.print(
                    f"[red]SZZ sırasında git başarısız:[/red] {(exc.stderr or '').strip()}"
                )
                raise typer.Exit(2) from exc
        years = config.history_years
        window = "tüm geçmiş" if years is None else f"{years} yıl"
        console.print(
            f"SZZ ({szz.variant}, {window}):{szz.fixes_in_window} fix → "
            f"[bold]{szz.fixes_with_inducing}[/bold] eşlendi · "
            f"[bold]{szz.inducing_commits}[/bold] bug-inducing commit · {szz.pairs} çift · "
            f"{szz.duration_seconds:.1f} sn"
        )
        console.print(
            f"[dim]Atlanan fix: {szz.fixes_skipped_large} çok büyük, "
            f"{szz.fixes_without_source} kaynak dosyasız (yalnız test/doküman vb.)[/dim]"
        )
    console.print(f"[dim]Çıktı: {out_dir}[/dim]")


def _fmt(value: float) -> str:
    return "—" if math.isnan(value) else f"{value:.3f}"


@app.command()
def train(
    repo: str = typer.Option(
        ...,
        "--repo",
        help="D1'deki repo (ör. scrapy__scrapy) ya da all: tüm repolarla genel model.",
    ),
    scenario: str = typer.Option(
        "within",
        "--scenario",
        help="within: repo kendi geçmişiyle; cross: diğer repolarla eğitilmiş genel model.",
    ),
    level: str = typer.Option(
        "commit", "--level", help="commit (d1.parquet) ya da pr (d1-pr.parquet, #73)."
    ),
    model: str = typer.Option("all", "--model", help="lr, rf, lightgbm veya all."),
    imbalance: str = typer.Option(
        "none", "--imbalance", help="Sınıf dengesizliği: none, weights, undersample veya smote."
    ),
    data_root: Path | None = typer.Option(
        None, "--data", help="Madencilik çıktılarının kökü (varsayılan: [mining].data_dir)."
    ),
    models_dir: Path = typer.Option(
        Path(".aegis/models"), "--models-dir", help="Eğitilen modellerin kaydedileceği dizin."
    ),
    report: Path | None = typer.Option(
        None, "--report", help="Metrikleri JSON olarak yaz (varsayılan: eval/reports/)."
    ),
    calibration: str | None = typer.Option(
        None,
        "--calibration",
        help="none, sigmoid veya isotonic (varsayılan: [training].calibration).",
    ),
    seed: int = typer.Option(0, "--seed", help="Rastgelelik tohumu."),
    config_path: Path | None = typer.Option(None, "--config", help="Yapılandırma dosyası."),
) -> None:
    """D1'deki bir repo için risk modellerini zaman sıralı bölmeyle eğitir ve değerlendirir.

    `--scenario cross` hedef reponun test kümesini, yalnızca diğer repolarla eğitilmiş bir modelle
    değerlendirir (soğuk başlangıç, #17). `--repo all` tüm repoların birleşik geçmişiyle bir genel
    model eğitir; D1'de olmayan yeni repolar bu modeli kullanır.
    """
    # scikit-learn yalnızca eğitimde gerekir; diğer komutlar (ör. review) onu yüklemez.
    from aegis.gatekeeper.model import FULL_FEATURES, IMBALANCE, MODELS, train_model
    from aegis.mining.prs import PR_FEATURES

    if TYPE_CHECKING:
        from aegis.gatekeeper.calibration import Method
        from aegis.gatekeeper.model import ModelName
    from aegis.gatekeeper.split import cross_split, time_split

    config = load_config(Path("."), config_path)
    names = list(MODELS) if model == "all" else [model]
    method = calibration or config.training.calibration
    if (
        method not in ("none", "sigmoid", "isotonic")
        or any(n not in MODELS for n in names)
        or imbalance not in IMBALANCE
        or scenario not in ("within", "cross")
        or (scenario == "cross" and repo == "all")
    ):
        console.print(
            "[red]--model lr|rf|lightgbm|all, --imbalance none|weights|undersample|smote, "
            "--scenario within|cross (cross ile --repo all kullanılamaz), "
            "--calibration none|sigmoid|isotonic[/red]"
        )
        raise typer.Exit(2)
    if level not in ("commit", "pr"):
        console.print("[red]--level commit|pr[/red]")
        raise typer.Exit(2)
    d1_name = "d1-pr.parquet" if level == "pr" else "d1.parquet"
    d1_path = (data_root or Path(config.mining.data_dir)) / d1_name
    if not d1_path.is_file():
        console.print(f"[red]{d1_path} yok; önce aegis dataset.[/red]")
        raise typer.Exit(2)
    d1 = pl.read_parquet(d1_path)
    rows = d1 if repo == "all" else d1.filter(pl.col("repo") == repo)
    if rows.height == 0:
        console.print(f"[red]D1'de {repo} için satır yok.[/red]")
        raise typer.Exit(2)
    try:
        if scenario == "cross":
            split = cross_split(d1, repo, config.training)
        else:
            split = time_split(rows, config.training)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    console.print(
        f"{repo} ({scenario}): eğitim {split.train.height} "
        f"({int(split.train['buggy'].sum())} hatalı) · "
        f"doğrulama {split.valid.height} · test {split.test.height} "
        f"({int(split.test['buggy'].sum())} hatalı) · tampon {config.training.label_delay_days} gün"
    )
    # F1, eşik ve diğer bütçeler rapordadır; tablo dar terminale sığsın.
    table = Table("Model", "ROC", "PR", "MCC", "R@20e", "Popt", "Brier", "ECE", "LLM≤%20 R")
    results: dict[str, Any] = {}
    for name in names:
        trained = train_model(
            split,
            cast("ModelName", name),
            imbalance=imbalance,
            calibration=cast("Method", method),
            seed=seed,
            features=PR_FEATURES if level == "pr" else FULL_FEATURES,
        )
        suffix = "-cross" if scenario == "cross" else ""
        prefix = "pr-" if level == "pr" else ""
        trained.save(models_dir / repo / f"{prefix}{name}-{imbalance}{suffix}.pkl")
        m = trained.test
        table.add_row(
            name, _fmt(m["roc_auc"]), _fmt(m["pr_auc"]), _fmt(m["mcc"]),
            _fmt(m["recall_at_20_effort"]), _fmt(m["popt"]), _fmt(m["brier"]), _fmt(m["ece"]),
            _fmt(trained.budget["0.2"]["recall"]),
        )  # fmt: skip
        results[name] = {
            "test": trained.test,
            "valid": trained.valid,
            "budget": trained.budget,
            "reliability": trained.reliability,
            **trained.meta,
        }
    console.print(table)
    suffix = "-cross" if scenario == "cross" else ""
    level_tag = "-pr" if level == "pr" else ""
    target = report or Path("eval/reports") / f"train{level_tag}-{repo}-{imbalance}{suffix}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "repo": repo,
        "level": level,
        "scenario": scenario,
        "imbalance": imbalance,
        "models": results,
    }
    target.write_text(json.dumps(payload, indent=2), "utf-8")
    console.print(
        f"[dim]Test kümesi metrikleri · modeller: {models_dir / repo} · rapor: {target}[/dim]"
    )


_BAND_STYLE = {RiskBand.LOW: "green", RiskBand.MEDIUM: "yellow", RiskBand.HIGH: "red"}


@app.command()
def score(
    range_: str | None = typer.Argument(
        None, metavar="[BASE..HEAD]", help="İncelenecek aralık; verilirse --base/--head yerine."
    ),
    base: str = typer.Option("main", "--base", help="Karşılaştırılacak taban dal/commit."),
    head: str = typer.Option("HEAD", "--head", help="İncelenecek dal/commit."),
    repo: Path = typer.Option(Path("."), "--repo", help="Git deposunun yolu."),
    model_path: Path | None = typer.Option(
        None,
        "--model",
        help="Model dosyası (.pkl). Verilirse [gatekeeper].mode yerine model kullanılır.",
    ),
    data_root: Path | None = typer.Option(
        None, "--data", help="Madencilik çıktılarının kökü (varsayılan: [mining].data_dir)."
    ),
    models_dir: Path = typer.Option(
        Path(".aegis/models"), "--models-dir", help="Eğitilmiş modellerin dizini."
    ),
) -> None:
    """Aralık için risk skoru, bant ve açıklama basar.

    `[gatekeeper].mode = "model"` ya da `--model` ile eğitilmiş model kullanılır: önce
    `<models-dir>/<repo>/lr-none.pkl`, yoksa genel model `<models-dir>/all/lr-none.pkl`.
    Model ya da reponun madencilik geçmişi yoksa sezgisel kurala dönülür.
    """
    from aegis.gatekeeper.factory import ModelGatekeeper, make_gatekeeper

    if range_ is not None:
        if ".." not in range_ or "..." in range_:
            console.print("[red]Aralık BASE..HEAD biçiminde olmalı.[/red]")
            raise typer.Exit(2)
        base, head = range_.split("..", 1)
    config = load_config(repo)
    try:
        text = git_diff(base, head, repo=repo)
    except subprocess.CalledProcessError as exc:
        console.print(f"[red]git diff başarısız:[/red] {exc.stderr.strip()}")
        raise typer.Exit(2) from exc

    gatekeeper, warning = make_gatekeeper(
        config, repo, base, head, model_path=model_path, data_root=data_root, models_dir=models_dir
    )
    if warning:
        console.print(f"[yellow]{warning}[/yellow]")
    if isinstance(gatekeeper, ModelGatekeeper):
        _score_with_model(gatekeeper)
        return

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


def _score_with_model(gk: "ModelGatekeeper") -> None:
    # scikit-learn yalnızca model kullanılırken yüklenir.
    from aegis.gatekeeper.score import load_history, range_commits, score_range

    commits = range_commits(gk.repo, gk.base, gk.head, gk.config)
    result = score_range(gk.model_path, commits, load_history(gk.data_dir), gk.config, gk.recent)
    path = gk.model_path
    style = _BAND_STYLE[result.band]
    console.print(f"Risk: [bold {style}]{result.score:.2f} ({result.band})[/bold {style}]")
    console.print(
        f"[dim]Model: {path} · bantlar: düşük < {result.low_threshold:.2f} ≤ orta < "
        f"{result.high_threshold:.2f} ≤ yüksek ({result.threshold_source}) · "
        f"{len(commits)} commit[/dim]"
    )
    for explanation in result.explanations:
        console.print(f"  • {explanation.text}")
    for sha, subject, prob in result.commits:
        console.print(f"[dim]  {sha[:10]} {prob:.2f} {subject}[/dim]")


@app.command()
def index(
    repo: Path = typer.Argument(Path("."), help="Madenciliği yapılmış yerel git deposu."),
    data_root: Path | None = typer.Option(
        None, "--data", help="Madencilik çıktılarının kökü (varsayılan: [mining].data_dir)."
    ),
    index_root: Path | None = typer.Option(
        None, "--index", help="Vektör indeksinin kökü (varsayılan: [memory].index_path)."
    ),
    rebuild: bool = typer.Option(False, "--rebuild", help="Kartları sıfırdan üret."),
    issue_titles: bool = typer.Option(
        False, "--issue-titles", help="Issue başlıklarını GitHub'dan oku (GITHUB_TOKEN gerekir)."
    ),
    config_path: Path | None = typer.Option(None, "--config", help="Yapılandırma dosyası."),
) -> None:
    """Bug-fix hafızasının hata kartlarını üretir; varsayılan olarak yalnızca yeni fix'leri ekler.

    Kartlar `<data>/<repo>/cards.jsonl` dosyasına yazılır (#22, #28). Embedding ve arama
    indeksi sonraki adımda (#24) bu kartlardan kurulur.
    """
    from aegis.memory.cards import build_cards, read_cards, write_cards
    from aegis.mining import repo_slug

    config = load_config(Path("."), config_path)
    slug = repo_slug(repo)
    data_dir = (data_root or Path(config.mining.data_dir)) / slug
    if not (data_dir / "commits.parquet").is_file():
        console.print(f"[red]{data_dir} altında madencilik çıktısı yok; önce aegis mine.[/red]")
        raise typer.Exit(2)
    titles = None
    if issue_titles:
        from aegis.mining.labels import github_issue_titles

        url = remote_url(repo)
        gh_repo = github_repository(url) if url else None
        token = os.environ.get("GITHUB_TOKEN")
        if gh_repo is None or not token:
            console.print("[red]--issue-titles için GitHub reposu ve GITHUB_TOKEN gerekir.[/red]")
            raise typer.Exit(2)
        titles = github_issue_titles(GitHubClient(token, gh_repo), data_dir / "issue_titles.json")
    path = data_dir / "cards.jsonl"
    existing = [] if rebuild else read_cards(path)
    skip = {c.fix_sha for c in existing}
    started = time.perf_counter()
    with Progress(
        TextColumn("{task.description}"), MofNCompleteColumn(), TimeElapsedColumn(), console=console
    ) as progress:
        task = progress.add_task(f"{slug} kartları", total=None)
        added = write_cards(
            path,
            build_cards(
                repo,
                data_dir,
                config,
                issue_titles=titles,
                skip=skip,
                on_card=lambda: progress.advance(task),
            ),
            append=not rebuild,
        )
    console.print(
        f"{slug}: {added} yeni kart · toplam {len(existing) + added} · "
        f"{time.perf_counter() - started:.1f} sn → {path}"
    )
    # Vektör indeksi her seferinde tüm kartlardan kurulur (LSA kartlar üzerinde eğitilir;
    # birkaç bin kart için saniyeler sürer).
    from aegis.memory.index import build_index, digest

    started = time.perf_counter()
    target = (index_root or Path(config.memory.index_path)) / slug
    index = build_index(read_cards(path), config.memory.embedding_model)
    index.save(target, digest(path))
    console.print(
        f"İndeks: {len(index.ids)} kart · {index.embedder.name} · "
        f"{time.perf_counter() - started:.1f} sn → {target}"
    )


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
    from aegis.gatekeeper.factory import make_gatekeeper

    gatekeeper, warning = make_gatekeeper(config, repo, base, head)
    if warning:
        console.print(f"[yellow]{warning}[/yellow]")
    result = run_review(
        text,
        config,
        ignore=load_ignore_spec(repo),
        metadata=metadata,
        llm_enabled=config.review.llm_enabled and not no_llm,
        cache=None if no_cache else ResponseCache(repo / config.review.cache_dir),
        gatekeeper=gatekeeper,
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


@app.command()
def dataset(
    data_root: Path | None = typer.Option(
        None, "--data", help="Madencilik çıktılarının kökü (varsayılan: [mining].data_dir)."
    ),
    out: Path | None = typer.Option(
        None, "--out", help="D1 Parquet dosyası (varsayılan: <data>/d1.parquet)."
    ),
    level: str = typer.Option(
        "commit",
        "--level",
        help="commit: D1; pr: PR düzeyinde D1 (d1-pr.parquet; önce commit düzeyi gerekir).",
    ),
    config_path: Path | None = typer.Option(None, "--config", help="Yapılandırma dosyası."),
) -> None:
    """Taranmış tüm repolardan D1 veri setini (Kamei özellikleri + SZZ etiketi) oluşturur."""
    config = load_config(Path("."), config_path).mining
    root = data_root or Path(config.data_dir)
    if not root.is_dir():
        console.print(f"[red]{root} bulunamadı; önce aegis mine.[/red]")
        raise typer.Exit(2)
    if level == "pr":
        _dataset_pr(root, Path(config.clone_dir), out or root / "d1-pr.parquet")
        return
    if level != "commit":
        console.print("[red]--level commit|pr[/red]")
        raise typer.Exit(2)
    target = out or root / "d1.parquet"
    stats = build_d1(root, target)
    if not stats:
        console.print(f"[yellow]{root} altında kamei ve SZZ çıktısı olan repo yok.[/yellow]")
        raise typer.Exit(1)
    table = Table("Repo", "Commit", "Fix", "Bug-inducing", "Oran", "≥ 200?")
    for s in stats:
        table.add_row(
            s.repo,
            str(s.commits),
            str(s.fixes),
            str(s.positives),
            f"%{100 * s.positive_rate:.1f}",
            "[green]evet[/green]" if s.enough else "[red]hayır[/red]",
        )
    console.print(table)
    console.print(f"[dim]Çıktı: {target} (+ {target.with_suffix('.json').name})[/dim]")


def _dataset_pr(root: Path, clone_root: Path, target: Path) -> None:
    from aegis.mining.prs import build_d1_pr

    d1 = root / "d1.parquet"
    if not d1.is_file():
        console.print(f"[red]{d1} yok; önce aegis dataset.[/red]")
        raise typer.Exit(2)
    stats = build_d1_pr(root, clone_root, d1, target)
    if not stats:
        console.print(f"[yellow]{clone_root} altında D1 repolarının klonu yok.[/yellow]")
        raise typer.Exit(1)
    table = Table("Repo", "PR", "Merge", "Squash", "Stil", "Hatalı", "Oran")
    for s in stats:
        table.add_row(
            s["repo"], str(s["prs"]), str(s["merge"]), str(s["squash"]), s["style"],
            str(s["positives"]), f"%{100 * s['positive_rate']:.1f}",
        )  # fmt: skip
    console.print(table)
    console.print(f"[dim]Çıktı: {target}[/dim]")


@app.command(name="eval")
def eval_() -> None:
    """Değerlendirme deneylerini koşturur. (Faz 7)"""
    _not_implemented("Faz 7")
