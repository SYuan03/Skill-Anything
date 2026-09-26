"""Deterministic quality checks for generated study packs."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from skill_anything.grounding import normalize_evidence
from skill_anything.models import QuestionType, SkillPack


@dataclass(frozen=True)
class AuditIssue:
    severity: str
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"severity": self.severity, "code": self.code, "message": self.message}


@dataclass
class PackAudit:
    issues: list[AuditIssue] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def errors(self) -> list[AuditIssue]:
        return [issue for issue in self.issues if issue.severity == "error"]

    @property
    def warnings(self) -> list[AuditIssue]:
        return [issue for issue in self.issues if issue.severity == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "metrics": self.metrics,
            "issues": [issue.to_dict() for issue in self.issues],
        }


def audit_pack(pack: SkillPack, *, strict: bool = False) -> PackAudit:
    """Audit a pack without an LLM or network call.

    Strict mode treats missing citations as errors, making the command suitable
    as a CI gate.  Non-strict mode keeps older v0.1-v0.4 packs usable while
    clearly reporting that their claims do not carry verifiable provenance.
    """
    report = PackAudit()
    if not pack.title.strip():
        _add(report, "error", "missing-title", "Pack title is empty.")
    if not pack.summary.strip():
        _add(report, "error", "missing-summary", "Pack summary is empty.")
    if not pack.detailed_notes.strip():
        _add(report, "warning", "missing-notes", "Detailed notes are empty.")

    collections = [
        ("quiz", pack.quiz_questions, lambda item: item.question),
        ("flashcard", pack.flashcards, lambda item: item.front),
        ("exercise", pack.practice_exercises, lambda item: item.title),
    ]
    interactive_total = sum(len(items) for _, items, _ in collections)
    if interactive_total == 0:
        _add(report, "error", "no-interactive-content", "Pack has no quiz, flashcard, or exercise items.")

    cited = 0
    for kind, items, identity in collections:
        seen: set[str] = set()
        for index, item in enumerate(items, 1):
            key = normalize_evidence(identity(item)).casefold()
            if key in seen:
                _add(report, "warning", f"duplicate-{kind}", f"Duplicate {kind} item at position {index}.")
            seen.add(key)

            citation = item.citation
            if citation and citation.section.strip() and citation.excerpt.strip():
                cited += 1
            else:
                severity = "error" if strict else "warning"
                _add(
                    report,
                    severity,
                    f"uncited-{kind}",
                    f"{kind.title()} item {index} has no source evidence.",
                )

    for index, question in enumerate(pack.quiz_questions, 1):
        if not question.answer.strip():
            _add(report, "error", "missing-answer", f"Quiz item {index} has no answer.")
        if not question.explanation.strip():
            _add(report, "warning", "missing-explanation", f"Quiz item {index} has no explanation.")
        if question.question_type in {QuestionType.MULTIPLE_CHOICE, QuestionType.SCENARIO}:
            options = [str(option).strip() for option in question.options if str(option).strip()]
            if len(options) != 4 or len({option.casefold() for option in options}) != 4:
                _add(
                    report,
                    "error",
                    "invalid-options",
                    f"Quiz item {index} must have four distinct options.",
                )
            elif not _answer_matches_option(question.answer, options):
                _add(
                    report,
                    "warning",
                    "answer-option-mismatch",
                    f"Quiz item {index} answer does not clearly match an option.",
                )
        if question.question_type == QuestionType.TRUE_FALSE and question.answer.casefold() not in {
            "true",
            "false",
        }:
            _add(report, "error", "invalid-true-false", f"Quiz item {index} answer must be True or False.")

    for index, card in enumerate(pack.flashcards, 1):
        if not card.front.strip() or not card.back.strip():
            _add(report, "error", "incomplete-flashcard", f"Flashcard {index} has an empty side.")

    for index, exercise in enumerate(pack.practice_exercises, 1):
        if not exercise.description.strip():
            _add(report, "error", "missing-description", f"Exercise {index} has no description.")
        if not exercise.solution.strip():
            _add(report, "warning", "missing-solution", f"Exercise {index} has no reference solution.")

    report.metrics = {
        "interactive_items": interactive_total,
        "cited_interactive_items": cited,
        "citation_coverage": round(cited / interactive_total, 4) if interactive_total else 0.0,
        "knowledge_evidence": len(pack.citations),
        "errors": len(report.errors),
        "warnings": len(report.warnings),
    }
    return report


def _answer_matches_option(answer: str, options: list[str]) -> bool:
    normalized = normalize_evidence(answer).casefold()
    if not normalized:
        return False
    if any(normalized == normalize_evidence(option).casefold() for option in options):
        return True
    label_match = re.match(r"^([a-d])(?:[.)]|\s*$)", normalized)
    if not label_match:
        return False
    label = label_match.group(1)
    return any(
        normalize_evidence(option).casefold().startswith(f"{label}.")
        or normalize_evidence(option).casefold().startswith(f"{label})")
        for option in options
    )


def _add(report: PackAudit, severity: str, code: str, message: str) -> None:
    report.issues.append(AuditIssue(severity=severity, code=code, message=message))
