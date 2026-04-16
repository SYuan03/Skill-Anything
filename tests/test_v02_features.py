"""Tests for v0.2 repo, import-skill, and lint functionality."""

from __future__ import annotations

from pathlib import Path

from skill_anything.engine import Engine
from skill_anything.linting import SkillLinter
from skill_anything.models import SourceType
from skill_anything.parsers.repo_parser import RepoParser


def test_engine_detect_source_type_for_repo_and_skill(tmp_path: Path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "README.md").write_text("# Demo\n", encoding="utf-8")

    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: demo-skill\ndescription: test\nversion: 1.0.0\n---\n# Demo Skill\n", encoding="utf-8")

    assert Engine._detect_source_type(str(repo_dir)) == SourceType.REPO
    assert Engine._detect_source_type(str(skill_dir)) == SourceType.SKILL
    assert Engine._detect_source_type("https://github.com/openai/openai-python") == SourceType.REPO


def test_repo_parser_local_repo_docs_first(tmp_path: Path):
    repo_dir = tmp_path / "demo-repo"
    (repo_dir / "docs").mkdir(parents=True)
    (repo_dir / "src").mkdir(parents=True)
    (repo_dir / "node_modules").mkdir(parents=True)
    (repo_dir / "README.md").write_text("# Demo Repo\n\nProject overview.", encoding="utf-8")
    (repo_dir / "docs" / "architecture.md").write_text("# Architecture\n\nSystem design notes.", encoding="utf-8")
    (repo_dir / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    (repo_dir / "src" / "main.py").write_text("def main():\n    return 'ok'\n", encoding="utf-8")
    (repo_dir / "node_modules" / "ignore.js").write_text("console.log('ignore')\n", encoding="utf-8")

    parser = RepoParser()
    chunks = parser.parse(str(repo_dir))

    assert chunks
    assert parser.stats["repo_mode"] == "local"
    assert parser.stats["selected_files"] >= 3
    assert "README.md" in parser.stats["selected_paths"]
    assert "docs/architecture.md" in parser.stats["selected_paths"]
    assert "node_modules/ignore.js" not in parser.stats["selected_paths"]


def test_repo_parser_github_uses_selected_files(monkeypatch):
    parser = RepoParser()
    fetched_paths: list[str] = []

    monkeypatch.setattr(
        parser,
        "_fetch_github_repo_info",
        lambda owner, repo: {"default_branch": "main", "full_name": f"{owner}/{repo}"},
    )
    monkeypatch.setattr(
        parser,
        "_fetch_github_tree",
        lambda owner, repo, branch: [
            {"type": "blob", "path": "README.md"},
            {"type": "blob", "path": "docs/setup.md"},
            {"type": "blob", "path": "src/main.py"},
            {"type": "blob", "path": "assets/logo.png"},
        ],
    )

    def fake_fetch_file(owner: str, repo: str, branch: str, path: str) -> str:
        fetched_paths.append(path)
        return f"# {path}\n\nContent for {path}\n"

    monkeypatch.setattr(parser, "_fetch_github_file", fake_fetch_file)

    chunks = parser.parse("https://github.com/acme/demo")

    assert chunks
    assert parser.stats["repo_mode"] == "github"
    assert parser.stats["total_files_scanned"] == 3
    assert "README.md" in fetched_paths
    assert "docs/setup.md" in fetched_paths
    assert "src/main.py" in fetched_paths
    assert "assets/logo.png" not in fetched_paths


def test_engine_import_skill_round_trip(sample_pack, tmp_path: Path):
    engine = Engine()
    engine.write(sample_pack, tmp_path, format="skill")

    skill_dir = tmp_path / "machine-learning-basics"
    imported = engine.from_skill(str(skill_dir))

    assert imported.source_type == SourceType.SKILL
    assert imported.title == "Machine Learning Basics"
    assert imported.summary == sample_pack.summary
    assert len(imported.quiz_questions) == len(sample_pack.quiz_questions)
    assert len(imported.flashcards) == len(sample_pack.flashcards)
    assert imported.metadata["skill_name"] == "machine-learning-basics"


def test_skill_linter_passes_exported_skill(sample_pack, tmp_path: Path):
    engine = Engine()
    engine.write(sample_pack, tmp_path, format="skill")

    result = SkillLinter().lint(str(tmp_path / "machine-learning-basics"))

    assert result.ok
    assert not result.errors


def test_skill_linter_reports_missing_frontmatter(tmp_path: Path):
    skill_dir = tmp_path / "broken-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# Broken Skill\n\n## Overview\n\nToo short.\n", encoding="utf-8")

    result = SkillLinter().lint(str(skill_dir))

    assert not result.ok
    assert any("frontmatter" in issue.message.lower() for issue in result.errors)


def test_skill_linter_reports_bad_asset_yaml(tmp_path: Path):
    skill_dir = tmp_path / "broken-assets"
    (skill_dir / "assets").mkdir(parents=True)
    (skill_dir / "scripts").mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: broken-assets\ndescription: broken\nversion: 1.0.0\n---\n# Broken Assets\n\n## Overview\n\nThis overview is long enough to avoid thin warnings.\n\n## Key Concepts\n\n1. First concept\n2. Second concept\n3. Third concept\n",
        encoding="utf-8",
    )
    (skill_dir / "assets" / "quiz.yaml").write_text("question: bad\n", encoding="utf-8")
    (skill_dir / "scripts" / "quiz.py").write_text("#!/usr/bin/env python3\n", encoding="utf-8")

    result = SkillLinter().lint(str(skill_dir))

    assert not result.ok
    assert any("yaml list" in issue.message.lower() for issue in result.errors)
