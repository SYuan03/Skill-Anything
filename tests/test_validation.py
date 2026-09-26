"""Tests for deterministic pack quality auditing."""

from __future__ import annotations

import copy
import json
from importlib.metadata import version
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from skill_anything.cli import app
from skill_anything.validation import audit_pack


def test_strict_audit_passes_fully_cited_pack(sample_pack) -> None:
    report = audit_pack(sample_pack, strict=True)

    assert report.ok
    assert report.metrics["citation_coverage"] == 1.0
    assert report.metrics["knowledge_evidence"] == 2


def test_strict_audit_rejects_uncited_and_malformed_items(sample_pack) -> None:
    pack = copy.deepcopy(sample_pack)
    pack.quiz_questions[0].citation = None
    pack.quiz_questions[0].options = ["A. same", "A. same"]

    report = audit_pack(pack, strict=True)

    assert not report.ok
    assert {issue.code for issue in report.errors} >= {"uncited-quiz", "invalid-options"}


def test_audit_cli_json_is_ci_friendly(sample_pack, tmp_path: Path) -> None:
    typer_version = tuple(int(part) for part in version("typer").split(".")[:2])
    if typer_version < (0, 16):
        pytest.skip("project requires Typer >=0.16; host test runner has an older Typer")
    pack_path = tmp_path / "pack.yaml"
    pack_path.write_text(
        yaml.safe_dump(sample_pack.to_dict(), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["audit", str(pack_path), "--strict", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["metrics"]["citation_coverage"] == 1.0
