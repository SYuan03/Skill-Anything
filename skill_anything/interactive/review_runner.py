"""Flashcard review runner — CLI-based spaced repetition review."""

from __future__ import annotations

import random

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from skill_anything.models import SkillPack

console = Console()


class ReviewRunner:
    """Run an interactive flashcard review session from a SkillPack."""

    def __init__(self, pack: SkillPack) -> None:
        self.pack = pack
        self.cards = list(pack.flashcards)
        self.known: list[int] = []
        self.reviewing: list[int] = []

    def run(self, *, shuffle: bool = True, count: int | None = None) -> None:
        indices = list(range(len(self.cards)))

        if shuffle:
            random.shuffle(indices)

        if count:
            indices = indices[:count]

        if not indices:
            console.print("[yellow]No flashcards available. Generate a skill pack first.[/yellow]")
            return

        console.print()
        console.print(
            Panel(
                f"[bold]{self.pack.title}[/bold]\n\n"
                f"[cyan]{len(indices)}[/cyan] flashcards\n"
                f"[bold]Enter[/bold] = flip  |  "
                f"[bold green]y[/bold green] = got it  |  "
                f"[bold red]n[/bold red] = need review  |  "
                f"[bold]q[/bold] = quit",
                title="Flashcard Review",
                border_style="magenta",
            )
        )

        round_num = 1
        while indices:
            console.print(f"\n[bold magenta]--- Round {round_num} ({len(indices)} cards) ---[/bold magenta]\n")
            next_round: list[int] = []

            for pos, idx in enumerate(indices):
                result = self._show_card(pos + 1, len(indices), idx)
                if result is None:
                    indices = []
                    break
                elif result:
                    self.known.append(idx)
                else:
                    self.reviewing.append(idx)
                    next_round.append(idx)

            if not next_round:
                break

            console.print(f"\n[yellow]{len(next_round)} card(s) need another round[/yellow]")

            indices = next_round
            self.reviewing = []
            round_num += 1

            if round_num > 5:
                console.print("[dim]Completed 5 rounds. Ending this session.[/dim]")
                break

        self._show_summary()

    def _show_card(self, num: int, total: int, card_idx: int) -> bool | None:
        card = self.cards[card_idx]

        tags_str = f"  [dim]{'  '.join(f'#{t}' for t in card.tags)}[/dim]" if card.tags else ""

        console.print(
            Panel(
                f"[bold]{card.front}[/bold]{tags_str}",
                title=f"Card {num}/{total}",
                border_style="blue",
                padding=(1, 3),
            )
        )

        try:
            console.input("[dim]  Press Enter to reveal...[/dim]")
        except (EOFError, KeyboardInterrupt):
            console.print()
            return None

        console.print(
            Panel(
                f"[green]{card.back}[/green]",
                title="Answer",
                border_style="green",
                padding=(1, 3),
            )
        )

        try:
            response = console.input(
                "  [green]y[/green]=got it  [red]n[/red]=review  [dim]q=quit[/dim]  > "
            ).strip().lower()
        except (EOFError, KeyboardInterrupt):
            console.print()
            return None

        if response == "q":
            return None

        console.print()
        return response != "n"

    def _show_summary(self) -> None:
        total = len(self.known) + len(self.reviewing)
        if total == 0:
            return

        console.print()
        console.print(
            Panel(
                f"[bold]Mastered:[/bold] [green]{len(self.known)}[/green]\n"
                f"[bold]Need review:[/bold] [red]{len(self.reviewing)}[/red]\n"
                f"[bold]Total:[/bold] {total}",
                title="Review Summary",
                border_style="magenta",
            )
        )

        if self.reviewing:
            table = Table(title="Cards to review again", border_style="red")
            table.add_column("Front", max_width=50)
            table.add_column("Tags", style="dim")

            for idx in self.reviewing:
                card = self.cards[idx]
                table.add_row(card.front[:50], ", ".join(card.tags))
            console.print(table)

        console.print()
