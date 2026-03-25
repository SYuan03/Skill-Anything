# -*- coding: utf-8 -*-
"""Skill-Anything CLI — Turn Any Knowledge Source Into Interactive Skills."""

from __future__ import annotations

import json
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
from skill_anything.models import SkillPack, slugify

app = typer.Typer(
    name="skill-anything",
    help="Skill-Anything: Turn Any Knowledge Source Into Interactive Skills",
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
[dim]Any Source -> Interactive Skills — v{version}[/dim]
"""


def _show_banner() -> None:
    console.print(_BANNER.format(version=__version__))


def _show_result(pack: SkillPack, output_dir: Path) -> None:
    console.print()
    summary_text = f"{pack.summary[:150]}..." if len(pack.summary) > 150 else pack.summary
    console.print(
        Panel(
            f"[bold green]Skill pack generated successfully![/bold green]\n\n"
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
    tree.add(f"[green]{slug}.yaml[/green]  <- data (use with quiz/review)")
    tree.add(f"[green]{slug}.md[/green]    <- study guide (read directly)")
    if (output_dir / f"{slug}-concept-map.png").exists():
        tree.add(f"[green]{slug}-concept-map.png[/green]  <- visual concept map")
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

    console.print()
    console.print(Panel(
        f"[bold]sa quiz[/bold] {output_dir / f'{slug}.yaml'}       [dim]# interactive quiz[/dim]\n"
        f"[bold]sa review[/bold] {output_dir / f'{slug}.yaml'}     [dim]# flashcard review[/dim]\n"
        f"[bold]sa info[/bold] {output_dir / f'{slug}.yaml'}       [dim]# view full details[/dim]",
        title="Next Steps",
        border_style="dim cyan",
    ))
    console.print()


# ======================================================================
# Source conversion commands
# ======================================================================

@app.command()
def pdf(
    path: str = typer.Argument(..., help="Path to PDF file"),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Skill pack title"),
    output: str = typer.Option("./output", "--output", "-o", help="Output directory"),
) -> None:
    """[bold cyan]PDF -> Skill[/bold cyan] Extract knowledge from a PDF and generate a full learning pack."""
    _show_banner()
    console.print(f"[bold]Parsing PDF:[/bold] [cyan]{path}[/cyan]\n")
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        progress.add_task("Extracting -> Notes -> Quiz -> Flashcards -> Exercises...", total=None)
        engine = Engine()
        pack = engine.from_pdf(path, title=title)
        engine.write(pack, output)
    _show_result(pack, Path(output))


@app.command()
def video(
    source: str = typer.Argument(..., help="YouTube URL or path to video/subtitle file"),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Skill pack title"),
    output: str = typer.Option("./output", "--output", "-o", help="Output directory"),
) -> None:
    """[bold cyan]Video -> Skill[/bold cyan] Extract knowledge from a video and generate a full learning pack."""
    _show_banner()
    console.print(f"[bold]Parsing video:[/bold] [cyan]{source}[/cyan]\n")
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        progress.add_task("Transcript -> Notes -> Quiz -> Flashcards -> Exercises...", total=None)
        engine = Engine()
        pack = engine.from_video(source, title=title)
        engine.write(pack, output)
    _show_result(pack, Path(output))


@app.command()
def web(
    url: str = typer.Argument(..., help="Webpage URL"),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Skill pack title"),
    output: str = typer.Option("./output", "--output", "-o", help="Output directory"),
) -> None:
    """[bold cyan]Web -> Skill[/bold cyan] Extract knowledge from a webpage and generate a full learning pack."""
    _show_banner()
    console.print(f"[bold]Fetching:[/bold] [cyan]{url}[/cyan]\n")
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        progress.add_task("Scraping -> Notes -> Quiz -> Flashcards -> Exercises...", total=None)
        engine = Engine()
        pack = engine.from_web(url, title=title)
        engine.write(pack, output)
    _show_result(pack, Path(output))


@app.command()
def text(
    source: str = typer.Argument(..., help="Path to text/Markdown file, or inline text"),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Skill pack title"),
    output: str = typer.Option("./output", "--output", "-o", help="Output directory"),
) -> None:
    """[bold cyan]Text -> Skill[/bold cyan] Generate a full learning pack from text or Markdown."""
    _show_banner()
    console.print(f"[bold]Parsing text:[/bold] [cyan]{source[:80]}[/cyan]\n")
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        progress.add_task("Extracting -> Notes -> Quiz -> Flashcards -> Exercises...", total=None)
        engine = Engine()
        pack = engine.from_text(source, title=title)
        engine.write(pack, output)
    _show_result(pack, Path(output))


@app.command()
def auto(
    source: str = typer.Argument(..., help="Any source: PDF path, YouTube URL, webpage URL, or text file"),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Skill pack title"),
    output: str = typer.Option("./output", "--output", "-o", help="Output directory"),
) -> None:
    """[bold green]Auto -> Skill[/bold green] Auto-detect source type and generate a full learning pack."""
    _show_banner()
    console.print(f"[bold]Auto-detecting:[/bold] [cyan]{source[:80]}[/cyan]\n")
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        progress.add_task("Detecting -> Extracting -> Generating skill pack...", total=None)
        engine = Engine()
        pack = engine.from_source(source, title=title)
        engine.write(pack, output)
    _show_result(pack, Path(output))


# ======================================================================
# Interactive modes
# ======================================================================

@app.command()
def quiz(
    path: str = typer.Argument(..., help="Path to skill pack YAML file"),
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
    path: str = typer.Argument(..., help="Path to skill pack YAML file"),
    count: Optional[int] = typer.Option(None, "--count", "-n", help="Number of flashcards"),
    no_shuffle: bool = typer.Option(False, "--no-shuffle", help="Keep original card order"),
) -> None:
    """[bold magenta]Review[/bold magenta] Flashcard review with multi-round repetition."""
    from skill_anything.interactive.review_runner import ReviewRunner
    pack = Engine.load(path)
    ReviewRunner(pack).run(count=count, shuffle=not no_shuffle)


# ======================================================================
# Utility
# ======================================================================

@app.command()
def info(
    path: str = typer.Argument(..., help="Path to skill pack YAML file"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """[bold yellow]Info[/bold yellow] View skill pack details."""
    pack = Engine.load(path)
    if json_output:
        rprint(json.dumps(pack.to_dict(), indent=2, ensure_ascii=False))
        return

    _show_banner()
    console.print(Panel(
        f"[bold]{pack.title}[/bold]\n\n"
        f"[bold]Source type:[/bold] {pack.source_type.value}\n"
        f"[bold]Source:[/bold] {pack.source_ref}",
        title="Skill Pack Info", border_style="cyan",
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

    console.print()


@app.command()
def version() -> None:
    """Show version."""
    rprint(f"[bold cyan]Skill-Anything[/bold cyan] v{__version__}")


if __name__ == "__main__":
    app()
