"""Repository parser — extract docs-first knowledge from local or GitHub repos."""

from __future__ import annotations

import fnmatch
import json
import logging
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from skill_anything.models import KnowledgeChunk, SourceType
from skill_anything.parsers.base import BaseParser
from skill_anything.parsers.text_parser import TextParser

log = logging.getLogger(__name__)


class RepoParser(BaseParser):
    """Parse repositories into docs-first knowledge chunks."""

    source_type = SourceType.REPO

    DOC_PATTERNS = ("README*", "docs/*", "doc/*", "*.md", "*.mdx", "*.rst", "*.txt")
    MANIFEST_FILES = {
        "pyproject.toml",
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "requirements.txt",
        "poetry.lock",
        "Pipfile",
        "Pipfile.lock",
        "go.mod",
        "go.sum",
        "Cargo.toml",
        "Cargo.lock",
        "Dockerfile",
        "docker-compose.yml",
        "docker-compose.yaml",
        "Makefile",
        ".env.example",
    }
    CODE_EXTENSIONS = {
        ".py",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".go",
        ".rs",
        ".java",
        ".kt",
        ".cs",
        ".rb",
        ".php",
        ".swift",
        ".scala",
        ".sh",
    }
    BINARY_EXTENSIONS = {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".svg",
        ".pdf",
        ".zip",
        ".tar",
        ".gz",
        ".bz2",
        ".7z",
        ".mp3",
        ".wav",
        ".mp4",
        ".mov",
        ".avi",
        ".woff",
        ".woff2",
        ".ttf",
        ".otf",
        ".ico",
    }
    IGNORED_DIRS = {
        ".git",
        ".github",
        ".idea",
        ".vscode",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "node_modules",
        "vendor",
        "dist",
        "build",
        "coverage",
        ".venv",
        "venv",
        "site-packages",
        "target",
        "out",
    }
    CODE_PRIORITY_NAMES = {
        "main",
        "app",
        "index",
        "server",
        "client",
        "api",
        "cli",
        "engine",
        "core",
        "service",
        "router",
        "__init__",
    }

    def __init__(self) -> None:
        self.stats: dict[str, Any] = {}

    def parse(self, source: str) -> list[KnowledgeChunk]:
        if self._is_github_repo_url(source):
            repo_label, selected = self._load_github_repo(source)
            mode = "github"
        else:
            repo_path = Path(source)
            if not repo_path.exists() or not repo_path.is_dir():
                raise FileNotFoundError(f"Repository directory not found: {source}")
            repo_label, candidates = self._load_local_repo(repo_path)
            selected = self._select_files(candidates)
            mode = "local"

        chunks = self._build_chunks(selected, source)
        self.stats = {
            "repo_mode": mode,
            "repo_label": repo_label,
            "total_files_scanned": self.stats.get(
                "total_files_scanned",
                len(candidates) if mode == "local" else len(selected),
            ),
            "selected_files": len(selected),
            "selected_paths": [entry["path"] for entry in selected],
        }
        return chunks

    @staticmethod
    def _is_github_repo_url(source: str) -> bool:
        parsed = urlparse(source)
        if parsed.scheme not in {"http", "https"} or parsed.netloc != "github.com":
            return False
        parts = [part for part in parsed.path.split("/") if part]
        return len(parts) >= 2

    def _load_local_repo(self, root: Path) -> tuple[str, list[dict[str, str]]]:
        candidates: list[dict[str, str]] = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [
                name for name in dirnames
                if name not in self.IGNORED_DIRS and not name.startswith(".cache")
            ]

            for filename in filenames:
                path = Path(dirpath) / filename
                rel_path = path.relative_to(root).as_posix()
                if not self._should_consider_path(rel_path):
                    continue
                try:
                    text = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                if not text.strip():
                    continue
                candidates.append({"path": rel_path, "content": text})

        return root.name, candidates

    def _load_github_repo(self, source: str) -> tuple[str, list[dict[str, str]]]:
        owner, repo = self._parse_github_repo(source)
        repo_info = self._fetch_github_repo_info(owner, repo)
        branch = repo_info.get("default_branch", "main")
        tree = self._fetch_github_tree(owner, repo, branch)

        tree_candidates: list[dict[str, str]] = []
        for item in tree:
            path = item.get("path", "")
            if item.get("type") == "blob" and self._should_consider_path(path):
                tree_candidates.append({"path": path, "content": ""})

        candidates: list[dict[str, str]] = []
        for entry in self._select_files(tree_candidates):
            text = self._fetch_github_file(owner, repo, branch, entry["path"])
            if text and text.strip():
                candidates.append({"path": entry["path"], "content": text})

        self.stats["total_files_scanned"] = len(tree_candidates)

        return repo_info.get("full_name", f"{owner}/{repo}"), candidates

    @staticmethod
    def _parse_github_repo(source: str) -> tuple[str, str]:
        parsed = urlparse(source)
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) < 2:
            raise ValueError(f"Expected a GitHub repository URL, got: {source}")
        owner, repo = parts[0], parts[1]
        return owner, repo.removesuffix(".git")

    def _fetch_github_repo_info(self, owner: str, repo: str) -> dict[str, Any]:
        url = f"https://api.github.com/repos/{owner}/{repo}"
        return self._fetch_json(url)

    def _fetch_github_tree(self, owner: str, repo: str, branch: str) -> list[dict[str, Any]]:
        url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
        data = self._fetch_json(url)
        return data.get("tree", [])

    def _fetch_github_file(self, owner: str, repo: str, branch: str, path: str) -> str:
        url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
        return self._fetch_text(url)

    @staticmethod
    def _fetch_json(url: str) -> dict[str, Any]:
        text = RepoParser._fetch_text(url)
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError(f"Expected a JSON object from {url}")
        return data

    @staticmethod
    def _fetch_text(url: str) -> str:
        headers = {"User-Agent": "Skill-Anything/0.2"}
        try:
            import httpx

            resp = httpx.get(url, follow_redirects=True, timeout=30.0, headers=headers)
            resp.raise_for_status()
            return resp.text
        except ImportError:
            import urllib.request

            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", errors="replace")

    def _should_consider_path(self, rel_path: str) -> bool:
        path = rel_path.strip("/")
        if not path:
            return False

        parts = path.split("/")
        if any(part in self.IGNORED_DIRS for part in parts[:-1]):
            return False
        if any(part.startswith(".cache") for part in parts[:-1]):
            return False

        suffix = Path(path).suffix.lower()
        if suffix in self.BINARY_EXTENSIONS:
            return False

        if Path(path).name.startswith(".") and Path(path).name not in {".env.example"}:
            return False

        return True

    def _select_files(self, candidates: list[dict[str, str]]) -> list[dict[str, str]]:
        docs = [entry for entry in candidates if self._classify_path(entry["path"]) == "docs"]
        manifests = [entry for entry in candidates if self._classify_path(entry["path"]) == "manifest"]
        code = [entry for entry in candidates if self._classify_path(entry["path"]) == "code"]

        docs.sort(key=lambda entry: self._docs_sort_key(entry["path"]))
        manifests.sort(key=lambda entry: self._manifest_sort_key(entry["path"]))
        code.sort(key=lambda entry: self._code_sort_key(entry["path"]))

        ordered = docs[:12] + manifests[:10] + code[:8]

        selected: list[dict[str, str]] = []
        seen: set[str] = set()
        for entry in ordered:
            if entry["path"] in seen:
                continue
            seen.add(entry["path"])
            selected.append(entry)

        return selected

    def _classify_path(self, rel_path: str) -> str:
        name = Path(rel_path).name
        if any(fnmatch.fnmatch(rel_path, pattern) for pattern in self.DOC_PATTERNS) or name.startswith("README"):
            return "docs"
        if name in self.MANIFEST_FILES:
            return "manifest"
        if Path(rel_path).suffix.lower() in self.CODE_EXTENSIONS:
            return "code"
        return "other"

    @staticmethod
    def _docs_sort_key(rel_path: str) -> tuple[int, int, str]:
        name = Path(rel_path).name.lower()
        return (0 if name.startswith("readme") else 1, rel_path.count("/"), rel_path.lower())

    @staticmethod
    def _manifest_sort_key(rel_path: str) -> tuple[int, str]:
        return (rel_path.count("/"), rel_path.lower())

    def _code_sort_key(self, rel_path: str) -> tuple[int, int, str]:
        path = Path(rel_path)
        stem = path.stem.lower()
        return (
            0 if stem in self.CODE_PRIORITY_NAMES else 1,
            rel_path.count("/"),
            rel_path.lower(),
        )

    def _build_chunks(self, selected: list[dict[str, str]], source: str) -> list[KnowledgeChunk]:
        text_parser = TextParser()
        chunks: list[KnowledgeChunk] = []
        chunk_index = 0

        for entry in selected:
            rel_path = entry["path"]
            text = entry["content"].strip()
            if not text:
                continue

            suffix = Path(rel_path).suffix.lower()
            if suffix in {".md", ".mdx", ".rst", ".txt"}:
                sections = text_parser._split_by_headings(text)
            else:
                sections = [(rel_path, text)]

            for heading, body in sections:
                if not body.strip():
                    continue
                for sub_chunk in self._split_into_chunks(body, max_chars=1800, overlap=120):
                    chunks.append(
                        KnowledgeChunk(
                            content=sub_chunk,
                            section=f"{rel_path} :: {heading or rel_path}",
                            chunk_index=chunk_index,
                            metadata={"source": source, "path": rel_path},
                        )
                    )
                    chunk_index += 1

        return chunks
