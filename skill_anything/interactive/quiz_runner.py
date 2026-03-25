"""Interactive quiz runner — CLI-based quiz with scoring and feedback."""

from __future__ import annotations

import random
import time

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from skill_anything.models import Difficulty, QuestionType, QuizQuestion, SkillPack

console = Console()


class QuizRunner:
    """Run an interactive quiz session from a SkillPack."""

    def __init__(self, pack: SkillPack) -> None:
        self.pack = pack
        self.questions = list(pack.quiz_questions)
        self.score = 0
        self.total = 0
        self.results: list[dict] = []

    def run(
        self,
        *,
        count: int | None = None,
        shuffle: bool = True,
        difficulty: str | None = None,
    ) -> None:
        questions = self._select_questions(count, shuffle, difficulty)

        if not questions:
            console.print("[yellow]No quiz questions available. Generate a skill pack first.[/yellow]")
            return

        console.print()
        console.print(
            Panel(
                f"[bold]{self.pack.title}[/bold]\n\n"
                f"[cyan]{len(questions)}[/cyan] questions\n"
                f"Type your answer (A/B/C/D or text). Press [bold]q[/bold] to quit.",
                title="Quiz Mode",
                border_style="cyan",
            )
        )
        console.print()

        start_time = time.time()

        for i, q in enumerate(questions):
            if not self._ask_question(i + 1, len(questions), q):
                break

        elapsed = time.time() - start_time
        self._show_results(elapsed)

    def _select_questions(
        self,
        count: int | None,
        shuffle: bool,
        difficulty: str | None,
    ) -> list[QuizQuestion]:
        questions = list(self.questions)

        if difficulty:
            try:
                diff = Difficulty(difficulty)
                questions = [q for q in questions if q.difficulty == diff]
            except ValueError:
                pass

        if shuffle:
            random.shuffle(questions)

        if count:
            questions = questions[:count]

        return questions

    def _ask_question(self, num: int, total: int, q: QuizQuestion) -> bool:
        diff_colors = {"easy": "green", "medium": "yellow", "hard": "red"}
        diff_color = diff_colors.get(q.difficulty.value, "white")

        type_labels = {
            QuestionType.MULTIPLE_CHOICE: "Multiple Choice",
            QuestionType.TRUE_FALSE: "True / False",
            QuestionType.FILL_BLANK: "Fill in the Blank",
            QuestionType.SHORT_ANSWER: "Short Answer",
            QuestionType.SCENARIO: "Scenario",
            QuestionType.COMPARISON: "Comparison",
        }

        console.print(f"[bold cyan]--- Q{num}/{total} ---[/bold cyan]  "
                      f"[{diff_color}]{q.difficulty.value.upper()}[/{diff_color}]  "
                      f"[dim]({type_labels.get(q.question_type, '')})[/dim]")
        console.print()
        console.print(f"  [bold]{q.question}[/bold]")
        console.print()

        if q.question_type in (QuestionType.MULTIPLE_CHOICE, QuestionType.SCENARIO) and q.options:
            for opt in q.options:
                console.print(f"    {opt}")
            console.print()

        elif q.question_type == QuestionType.TRUE_FALSE:
            console.print("    A. True")
            console.print("    B. False")
            console.print()

        elif q.question_type in (QuestionType.SHORT_ANSWER, QuestionType.COMPARISON):
            console.print("  [dim]Type your answer and press Enter. Type 's' to skip and see the reference answer.[/dim]")
            console.print()

        elif q.question_type == QuestionType.FILL_BLANK:
            console.print("  [dim]Type your answer[/dim]")
            console.print()

        try:
            user_input = console.input("[bold cyan]  Answer > [/bold cyan]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            return False

        if user_input.lower() == "q":
            return False

        self.total += 1

        is_open = q.question_type in (QuestionType.SHORT_ANSWER, QuestionType.COMPARISON, QuestionType.SCENARIO)
        skipped = is_open and user_input.lower() == "s"

        if is_open and not skipped:
            console.print(f"\n  [bold]Reference answer:[/bold] [green]{q.answer}[/green]")
            if q.explanation:
                console.print(f"  [dim]{q.explanation}[/dim]")
            try:
                self_eval = console.input("\n  [bold cyan]Did you get it right? (y/n) > [/bold cyan]").strip().lower()
            except (EOFError, KeyboardInterrupt):
                self_eval = "n"
            correct = self_eval == "y"
        elif skipped:
            correct = False
            console.print(f"\n  [bold]Reference answer:[/bold] [green]{q.answer}[/green]")
        else:
            correct = self._check_answer(user_input, q)

        if correct:
            self.score += 1
            if not is_open:
                console.print("  [bold green]Correct![/bold green]")
        elif not is_open:
            console.print(f"  [bold red]Incorrect.[/bold red]  Answer: [green]{q.answer}[/green]")

        if q.explanation and not is_open:
            console.print(f"  [dim]{q.explanation}[/dim]")

        console.print()
        self.results.append({
            "question": q.question[:50],
            "correct": correct,
            "difficulty": q.difficulty.value,
        })
        return True

    @staticmethod
    def _check_answer(user_input: str, q: QuizQuestion) -> bool:
        user = user_input.strip().upper()
        answer = q.answer.strip()

        if user == answer.upper():
            return True

        if len(user) == 1 and q.options:
            for opt in q.options:
                if opt.upper().startswith(user + ".") or opt.upper().startswith(user + " "):
                    return opt.strip() == answer.strip()

        if q.question_type == QuestionType.TRUE_FALSE:
            true_answers = {"A", "TRUE", "T", "YES", "Y"}
            false_answers = {"B", "FALSE", "F", "NO", "N"}
            answer_is_true = answer.upper() in {"TRUE", "T", "YES"}
            if user in true_answers and answer_is_true:
                return True
            if user in false_answers and not answer_is_true:
                return True

        if user.lower() == answer.lower():
            return True

        return user in answer.upper() or answer.upper() in user

    def _show_results(self, elapsed: float) -> None:
        if self.total == 0:
            return

        pct = (self.score / self.total) * 100
        if pct >= 90:
            grade, color = "A", "bold green"
        elif pct >= 80:
            grade, color = "B", "green"
        elif pct >= 70:
            grade, color = "C", "yellow"
        elif pct >= 60:
            grade, color = "D", "red"
        else:
            grade, color = "F", "bold red"

        mins = int(elapsed) // 60
        secs = int(elapsed) % 60

        console.print(
            Panel(
                f"[bold]Score:[/bold] [{color}]{self.score}/{self.total} ({pct:.0f}%)[/{color}]\n"
                f"[bold]Grade:[/bold] [{color}]{grade}[/{color}]\n"
                f"[bold]Time:[/bold] {mins}m {secs}s",
                title="Results",
                border_style="cyan",
            )
        )

        if self.results:
            table = Table(border_style="dim")
            table.add_column("#", width=4)
            table.add_column("Question", max_width=40)
            table.add_column("Difficulty", width=10)
            table.add_column("Result", width=6)

            for i, r in enumerate(self.results):
                status = "[green]Pass[/green]" if r["correct"] else "[red]Fail[/red]"
                table.add_row(str(i + 1), r["question"], r["difficulty"], status)
            console.print(table)

        console.print()
