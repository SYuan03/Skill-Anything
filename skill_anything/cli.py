# -*- coding: utf-8 -*-
"""Skill-Anything CLI — build study packs from source material and optionally export AI skills."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.tree import Tree

from skill_anything import __version__
from skill_anything.engine import Engine
from skill_anything.linting import SkillLinter
from skill_anything.models import SkillPack, slugify

app = typer.Typer(
    name="skill-anything",
    help="Skill-Anything: turn source material, repos, and skills into study packs and SKILL.md exports",
    add_completion=False,
    no_args_is_help=True,
    rich_markup_mode="rich",
)
console = Console()

_BANNER = r"""[bold cyan]
  ____  _    _ _ _        _                _   _     _
 / ___|| | _(_) | |      / \   _ __  _   _| |_| |__ (_)_ __   __ _
 \___ \| |/ / | | |___  / _ \ | '_ \| | | | __| '_ \| | '_ \ / _` |
  ___) |   <| | | |___ / ___ \| | | | |_| | |_| | | | | | | | (_| |
 |____/|_|\_\_|_|_|   /_/   \_\_| |_|\__, |\__|_| |_|_|_| |_|\__, |
                                      |___/                    |___/
[/bold cyan]
[dim]Any Source -> Study Pack -> Optional Skill Export — v{version}[/dim]
"""


def _show_banner() -> None:
    console.print(_BANNER.format(version=__version__))


def _handle_error(e: Exception) -> None:
    """Print a user-friendly error message and exit."""
    error_type = type(e).__name__
    console.print(f"\n[bold red]Error:[/bold red] {error_type}: {e}")
    console.print("[dim]Run with PYTHONUNBUFFERED=1 for full traceback.[/dim]")
    raise typer.Exit(1)


def _show_result(pack: SkillPack, output_dir: Path, *, format: str = "study") -> None:
    console.print()
    summary_text = f"{pack.summary[:150]}..." if len(pack.summary) > 150 else pack.summary
    console.print(
        Panel(
            f"[bold green]Pack generated successfully![/bold green]\n\n"
            f"[bold]{pack.title}[/bold]\n"
            f"[dim]{summary_text}[/dim]",
            title="Skill-Anything",
            border_style="cyan",
        )
    )

    stats = pack.stats
    table = Table(title="Generated Content", border_style="cyan")
    table.add_column("Category", style="bold")
    table.add_column("Count", justify="right", style="cyan")
    table.add_column("Description", style="dim")

    stat_labels = [
        ("key_concepts", "Key Concepts", "Core knowledge points"),
        ("glossary", "Glossary", "Terms and definitions"),
        ("timeline", "Outline", "Content structure"),
        ("quiz_questions", "Quiz Questions", "MCQ / T-F / Scenario / Comparison / ..."),
        ("flashcards", "Flashcards", "Spaced repetition cards"),
        ("exercises", "Exercises", "Hands-on practice tasks"),
        ("takeaways", "Takeaways", "Actionable next steps"),
    ]
    for key, label, desc in stat_labels:
        count = stats.get(key, 0)
        if count > 0:
            table.add_row(label, str(count), desc)

    table.add_row("Detailed Notes", "Y" if pack.detailed_notes else "-", "Structured study notes")
    table.add_row("Cheat Sheet", "Y" if pack.cheat_sheet else "-", "One-page quick reference")
    table.add_row("Learning Path", "Y" if pack.learning_path else "-", "Prerequisites + next steps + resources")
    console.print(table)

    slug = slugify(pack.title)
    tree = Tree(f"[bold]{output_dir}[/bold]")

    if format in ("study", "all"):
        tree.add(f"[green]{slug}.yaml[/green]  <- structured pack data (use with quiz/review/info)")
        tree.add(f"[green]{slug}.md[/green]    <- study guide (read directly)")
        if (output_dir / f"{slug}-concept-map.png").exists():
            tree.add(f"[green]{slug}-concept-map.png[/green]  <- visual concept map")

    if format in ("skill", "all"):
        skill_tree = tree.add(f"[cyan]{slug}/[/cyan]  <- agent-ready SKILL.md export")
        skill_dir = output_dir / slug
        if skill_dir.exists():
            skill_tree.add("[green]SKILL.md[/green]")
            if (skill_dir / "references").exists():
                refs = skill_tree.add("[dim]references/[/dim]")
                for f in sorted((skill_dir / "references").iterdir()):
                    refs.add(f"[green]{f.name}[/green]")
            if (skill_dir / "assets").exists():
                assets = skill_tree.add("[dim]assets/[/dim]")
                for f in sorted((skill_dir / "assets").iterdir()):
                    assets.add(f"[green]{f.name}[/green]")
            if (skill_dir / "scripts").exists():
                scripts = skill_tree.add("[dim]scripts/[/dim]")
                for f in sorted((skill_dir / "scripts").iterdir()):
                    scripts.add(f"[green]{f.name}[/green]")

    console.print()
    console.print(tree)

    if pack.key_concepts:
        console.print("\n[bold cyan]Key Concepts:[/bold cyan]")
        for i, concept in enumerate(pack.key_concepts[:5], 1):
            console.print(f"  [dim]{i}.[/dim] {concept}")
        if len(pack.key_concepts) > 5:
            console.print(f"  [dim]... {len(pack.key_concepts) - 5} more[/dim]")

    if pack.takeaways:
        console.print("\n[bold cyan]Takeaways:[/bold cyan]")
        for t in pack.takeaways[:3]:
            console.print(f"  {t}")
        if len(pack.takeaways) > 3:
            console.print(f"  [dim]... {len(pack.takeaways) - 3} more[/dim]")

    metadata_lines: list[str] = []
    if pack.source_type.value == "repo":
        metadata_lines.append(f"[bold]Repo mode:[/bold] {pack.metadata.get('repo_mode', '-')}")
        metadata_lines.append(
            f"[bold]Files scanned:[/bold] {pack.metadata.get('total_files_scanned', '-')}"
        )
        metadata_lines.append(
            f"[bold]Files selected:[/bold] {pack.metadata.get('selected_files', '-')}"
        )
    if pack.source_type.value == "skill":
        metadata_lines.append(
            f"[bold]Imported from:[/bold] {pack.metadata.get('imported_from', pack.source_ref)}"
        )
        metadata_lines.append(
            f"[bold]Assets:[/bold] {len(pack.metadata.get('asset_files', []))}"
        )
        metadata_lines.append(
            f"[bold]References:[/bold] {len(pack.metadata.get('reference_files', []))}"
        )
    if metadata_lines:
        console.print()
        console.print(
            Panel("\n".join(metadata_lines), title="Source Metadata", border_style="blue")
        )

    console.print()

    if format == "study":
        console.print(Panel(
            f"[bold]sa quiz[/bold] {output_dir / f'{slug}.yaml'}       [dim]# interactive quiz[/dim]\n"
            f"[bold]sa review[/bold] {output_dir / f'{slug}.yaml'}     [dim]# flashcard review[/dim]\n"
            f"[bold]sa info[/bold] {output_dir / f'{slug}.yaml'}       [dim]# view full details[/dim]",
            title="Next Steps",
            border_style="dim cyan",
        ))
    elif format == "all":
        console.print(Panel(
            f"[bold]sa quiz[/bold] {output_dir / f'{slug}.yaml'}       [dim]# interactive quiz[/dim]\n"
            f"[bold]sa review[/bold] {output_dir / f'{slug}.yaml'}     [dim]# flashcard review[/dim]\n"
            f"[bold]sa info[/bold] {output_dir / f'{slug}.yaml'}       [dim]# view full details[/dim]\n"
            f"[bold]cp -r[/bold] {output_dir / slug} ~/.claude/skills/  [dim]# optional AI skill export[/dim]",
            title="Next Steps",
            border_style="dim cyan",
        ))
    elif format == "skill":
        console.print(Panel(
            f"[bold]Copy to your AI tool's skills directory:[/bold]\n"
            f"  cp -r {output_dir / slug} ~/.claude/skills/\n"
            f"  cp -r {output_dir / slug} ~/.cursor/skills/\n"
            f"  cp -r {output_dir / slug} .claude/skills/",
            title="Use as AI Skill",
            border_style="dim cyan",
        ))
    console.print()


# ======================================================================
# Source conversion commands
# ======================================================================

@app.command()
def pdf(
    path: str = typer.Argument(..., help="Path to PDF file"),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Generated pack title"),
    output: str = typer.Option("./output", "--output", "-o", help="Output directory"),
    format: str = typer.Option("study", "--format", "-f", help="Output format: study, skill, or all"),
) -> None:
    """[bold cyan]PDF -> Study Pack[/bold cyan] Extract knowledge from a PDF and generate a full learning pack."""
    _show_banner()
    console.print(f"[bold]Parsing PDF:[/bold] [cyan]{path}[/cyan]\n")
    try:
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
            progress.add_task("Extracting -> Notes -> Quiz -> Flashcards -> Exercises...", total=None)
            engine = Engine()
            pack = engine.from_pdf(path, title=title)
            engine.write(pack, output, format=format)
        _show_result(pack, Path(output), format=format)
    except typer.Exit:
        raise
    except Exception as e:
        _handle_error(e)


@app.command()
def video(
    source: str = typer.Argument(..., help="YouTube URL or path to video/subtitle file"),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Generated pack title"),
    output: str = typer.Option("./output", "--output", "-o", help="Output directory"),
    format: str = typer.Option("study", "--format", "-f", help="Output format: study, skill, or all"),
) -> None:
    """[bold cyan]Video -> Study Pack[/bold cyan] Extract knowledge from a video and generate a full learning pack."""
    _show_banner()
    console.print(f"[bold]Parsing video:[/bold] [cyan]{source}[/cyan]\n")
    try:
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
            progress.add_task("Transcript -> Notes -> Quiz -> Flashcards -> Exercises...", total=None)
            engine = Engine()
            pack = engine.from_video(source, title=title)
            engine.write(pack, output, format=format)
        _show_result(pack, Path(output), format=format)
    except typer.Exit:
        raise
    except Exception as e:
        _handle_error(e)


@app.command()
def web(
    url: str = typer.Argument(..., help="Webpage URL"),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Generated pack title"),
    output: str = typer.Option("./output", "--output", "-o", help="Output directory"),
    format: str = typer.Option("study", "--format", "-f", help="Output format: study, skill, or all"),
) -> None:
    """[bold cyan]Web -> Study Pack[/bold cyan] Extract knowledge from a webpage and generate a full learning pack."""
    _show_banner()
    console.print(f"[bold]Fetching:[/bold] [cyan]{url}[/cyan]\n")
    try:
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
            progress.add_task("Scraping -> Notes -> Quiz -> Flashcards -> Exercises...", total=None)
            engine = Engine()
            pack = engine.from_web(url, title=title)
            engine.write(pack, output, format=format)
        _show_result(pack, Path(output), format=format)
    except typer.Exit:
        raise
    except Exception as e:
        _handle_error(e)


@app.command()
def text(
    source: str = typer.Argument(..., help="Path to text/Markdown file, or inline text"),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Generated pack title"),
    output: str = typer.Option("./output", "--output", "-o", help="Output directory"),
    format: str = typer.Option("study", "--format", "-f", help="Output format: study, skill, or all"),
) -> None:
    """[bold cyan]Text -> Study Pack[/bold cyan] Generate a full learning pack from text or Markdown."""
    _show_banner()
    console.print(f"[bold]Parsing text:[/bold] [cyan]{source[:80]}[/cyan]\n")
    try:
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
            progress.add_task("Extracting -> Notes -> Quiz -> Flashcards -> Exercises...", total=None)
            engine = Engine()
            pack = engine.from_text(source, title=title)
            engine.write(pack, output, format=format)
        _show_result(pack, Path(output), format=format)
    except typer.Exit:
        raise
    except Exception as e:
        _handle_error(e)


@app.command()
def audio(
    path: str = typer.Argument(..., help="Path to audio file (.mp3, .wav, .m4a, .aac, .flac, .ogg, .wma)"),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Generated pack title"),
    output: str = typer.Option("./output", "--output", "-o", help="Output directory"),
    format: str = typer.Option("study", "--format", "-f", help="Output format: study, skill, or all"),
) -> None:
    """[bold cyan]Audio -> Study Pack[/bold cyan] Transcribe audio and generate a full learning pack."""
    _show_banner()
    console.print(f"[bold]Transcribing audio:[/bold] [cyan]{path}[/cyan]\n")
    try:
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
            progress.add_task("Transcribing -> Notes -> Quiz -> Flashcards -> Exercises...", total=None)
            engine = Engine()
            pack = engine.from_audio(path, title=title)
            engine.write(pack, output, format=format)
        _show_result(pack, Path(output), format=format)
    except typer.Exit:
        raise
    except Exception as e:
        _handle_error(e)


@app.command()
def auto(
    source: str = typer.Argument(
        ...,
        help="Any source: PDF, YouTube URL, webpage, audio file, repo path, GitHub repo, skill dir, or text file",
    ),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Generated pack title"),
    output: str = typer.Option("./output", "--output", "-o", help="Output directory"),
    format: str = typer.Option("study", "--format", "-f", help="Output format: study, skill, or all"),
) -> None:
    """[bold green]Auto -> Pack[/bold green] Auto-detect source type and generate a full learning pack."""
    _show_banner()
    console.print(f"[bold]Auto-detecting:[/bold] [cyan]{source[:80]}[/cyan]\n")
    try:
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
            progress.add_task("Detecting -> Extracting -> Generating study pack...", total=None)
            engine = Engine()
            pack = engine.from_source(source, title=title)
            engine.write(pack, output, format=format)
        _show_result(pack, Path(output), format=format)
    except typer.Exit:
        raise
    except Exception as e:
        _handle_error(e)


@app.command()
def repo(
    source: str = typer.Argument(..., help="Path to a local repository or a public GitHub repo URL"),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Generated pack title"),
    output: str = typer.Option("./output", "--output", "-o", help="Output directory"),
    format: str = typer.Option("study", "--format", "-f", help="Output format: study, skill, or all"),
) -> None:
    """[bold cyan]Repo -> Study Pack[/bold cyan] Extract onboarding knowledge from a code repository."""
    _show_banner()
    console.print(f"[bold]Scanning repository:[/bold] [cyan]{source}[/cyan]\n")
    try:
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
            progress.add_task("Docs-first scan -> Notes -> Quiz -> Flashcards -> Exercises...", total=None)
            engine = Engine()
            pack = engine.from_repo(source, title=title)
            engine.write(pack, output, format=format)
        _show_result(pack, Path(output), format=format)
    except typer.Exit:
        raise
    except Exception as e:
        _handle_error(e)


@app.command("import-skill")
def import_skill(
    source: str = typer.Argument(..., help="Path to a skill directory or SKILL.md file"),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Generated pack title"),
    output: str = typer.Option("./output", "--output", "-o", help="Output directory"),
    format: str = typer.Option("study", "--format", "-f", help="Output format: study, skill, or all"),
) -> None:
    """[bold cyan]Import Skill[/bold cyan] Convert an existing SKILL.md package back into a study pack."""
    _show_banner()
    console.print(f"[bold]Importing skill:[/bold] [cyan]{source}[/cyan]\n")
    try:
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
            progress.add_task("Importing -> Rebuilding study pack -> Exporting...", total=None)
            engine = Engine()
            pack = engine.from_skill(source, title=title)
            engine.write(pack, output, format=format)
        _show_result(pack, Path(output), format=format)
    except typer.Exit:
        raise
    except Exception as e:
        _handle_error(e)


@app.command()
def lint(
    source: str = typer.Argument(..., help="Path to a skill directory or SKILL.md file"),
) -> None:
    """[bold yellow]Lint[/bold yellow] Validate a SKILL.md package for packaging and data issues."""
    _show_banner()
    console.print(f"[bold]Linting skill:[/bold] [cyan]{source}[/cyan]\n")

    result = SkillLinter().lint(source)

    if result.errors:
        error_table = Table(title="Errors", border_style="red")
        error_table.add_column("Path", style="bold red")
        error_table.add_column("Message")
        for issue in result.errors:
            error_table.add_row(issue.path or "-", issue.message)
        console.print(error_table)

    if result.warnings:
        warning_table = Table(title="Warnings", border_style="yellow")
        warning_table.add_column("Path", style="bold yellow")
        warning_table.add_column("Message")
        for issue in result.warnings:
            warning_table.add_row(issue.path or "-", issue.message)
        console.print(warning_table)

    if result.ok:
        console.print(Panel("[bold green]No blocking errors found.[/bold green]", title="Lint Result", border_style="green"))
        return

    raise typer.Exit(1)


# ======================================================================
# Interactive modes
# ======================================================================

@app.command()
def quiz(
    path: str = typer.Argument(..., help="Path to generated pack YAML file"),
    count: Optional[int] = typer.Option(None, "--count", "-n", help="Number of questions"),
    difficulty: Optional[str] = typer.Option(None, "--difficulty", "-d", help="Filter: easy/medium/hard"),
    no_shuffle: bool = typer.Option(False, "--no-shuffle", help="Keep original question order"),
) -> None:
    """[bold green]Quiz[/bold green] Interactive knowledge quiz (6 question types)."""
    from skill_anything.interactive.quiz_runner import QuizRunner
    pack = Engine.load(path)
    QuizRunner(pack).run(count=count, shuffle=not no_shuffle, difficulty=difficulty)


@app.command()
def review(
    path: str = typer.Argument(..., help="Path to generated pack YAML file"),
    count: Optional[int] = typer.Option(None, "--count", "-n", help="Number of flashcards"),
    no_shuffle: bool = typer.Option(False, "--no-shuffle", help="Keep original card order"),
) -> None:
    """[bold magenta]Review[/bold magenta] Flashcard review with multi-round repetition."""
    from skill_anything.interactive.review_runner import ReviewRunner
    pack = Engine.load(path)
    ReviewRunner(pack).run(count=count, shuffle=not no_shuffle)


# ======================================================================
# Export
# ======================================================================

@app.command()
def export(
    path: str = typer.Argument(..., help="Path to generated pack YAML file"),
    format: str = typer.Option("skill", "--format", "-f", help="Export format: study, skill, or all"),
    output: str = typer.Option("./output", "--output", "-o", help="Output directory"),
) -> None:
    """[bold yellow]Export[/bold yellow] Convert an existing YAML pack to a different format.

    Export as SKILL.md directory (Claude Code / Cursor / Codex compatible):
      sa export output/my-skill.yaml --format skill

    Export as study guide (Markdown):
      sa export output/my-skill.yaml --format study

    Export both formats:
      sa export output/my-skill.yaml --format all
    """
    _show_banner()
    console.print(f"[bold]Loading:[/bold] [cyan]{path}[/cyan]")
    console.print(f"[bold]Format:[/bold] [cyan]{format}[/cyan]\n")
    pack = Engine.load(path)
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        progress.add_task(f"Exporting as {format}...", total=None)
        engine = Engine()
        engine.write(pack, output, format=format)
    _show_result(pack, Path(output), format=format)


# ======================================================================
# Utility
# ======================================================================

@app.command()
def info(
    path: str = typer.Argument(..., help="Path to generated pack YAML file"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """[bold yellow]Info[/bold yellow] View generated pack details."""
    pack = Engine.load(path)
    if json_output:
        rprint(json.dumps(pack.to_dict(), indent=2, ensure_ascii=False))
        return

    _show_banner()
    console.print(Panel(
        f"[bold]{pack.title}[/bold]\n\n"
        f"[bold]Source type:[/bold] {pack.source_type.value}\n"
        f"[bold]Source:[/bold] {pack.source_ref}",
        title="Pack Info", border_style="cyan",
    ))

    stats = pack.stats
    table = Table(border_style="cyan")
    table.add_column("Item", style="bold")
    table.add_column("Count", justify="right")
    for key, label in [("key_concepts", "Key Concepts"), ("glossary", "Glossary"),
                       ("timeline", "Outline"), ("quiz_questions", "Quiz Questions"),
                       ("flashcards", "Flashcards"), ("exercises", "Exercises"),
                       ("takeaways", "Takeaways")]:
        val = stats.get(key, 0)
        if val:
            table.add_row(label, str(val))
    console.print(table)

    console.print(f"\n[bold]Summary:[/bold]\n  {pack.summary}")

    if pack.key_concepts:
        console.print("\n[bold]Key Concepts:[/bold]")
        for i, c in enumerate(pack.key_concepts, 1):
            console.print(f"  {i}. {c}")

    if pack.glossary:
        console.print("\n[bold]Glossary:[/bold]")
        g_table = Table(border_style="dim")
        g_table.add_column("Term", style="bold", max_width=20)
        g_table.add_column("Definition", max_width=60)
        for g in pack.glossary[:10]:
            g_table.add_row(g.term, g.definition[:60])
        console.print(g_table)

    if pack.takeaways:
        console.print("\n[bold]Takeaways:[/bold]")
        for t in pack.takeaways:
            console.print(f"  {t}")

    if pack.learning_path:
        console.print("\n[bold]Learning Path:[/bold]")
        for section, items in pack.learning_path.items():
            label = {"prerequisites": "Prerequisites", "next_steps": "Next Steps", "resources": "Resources"}.get(section, section)
            console.print(f"  [bold]{label}:[/bold]")
            for item in items:
                console.print(f"    - {item}")

    interesting_metadata = {
        key: value
        for key, value in pack.metadata.items()
        if key in {"repo_mode", "repo_label", "total_files_scanned", "selected_files", "imported_from", "skill_name"}
    }
    if interesting_metadata:
        console.print("\n[bold]Metadata:[/bold]")
        for key, value in interesting_metadata.items():
            console.print(f"  [bold]{key}:[/bold] {value}")

    console.print()


@app.command()
def version() -> None:
    """Show version."""
    rprint(f"[bold cyan]Skill-Anything[/bold cyan] v{__version__}")


if __name__ == "__main__":
    app()
