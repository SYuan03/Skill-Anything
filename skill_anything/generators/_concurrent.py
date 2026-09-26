"""Concurrent LLM execution with disk cache and progress reporting.

The v0.3 map-reduce pipeline fans out one LLM call per Section (often dozens
on a book or large repo). This module gives those calls three properties they
lacked in v0.2:

1. **Concurrency**: LLM calls are IO-bound; running them serially wastes time.
2. **Disk cache**: rerunning on the same source (same prompts, same model)
   shouldn't pay tokens twice. Cache is keyed by sha256(prompt + model + version).
3. **Per-item failure isolation**: one section failing must not lose the
   results of sections that already succeeded.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, TypeVar

from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

log = logging.getLogger(__name__)

T = TypeVar("T")
R = TypeVar("R")


def resolve_fast_model(override: str | None = None) -> str:
    """Pick the 'fast' model for per-section work.

    Resolution order: explicit override -> SKILL_ANYTHING_MODEL_FAST env ->
    SKILL_ANYTHING_MODEL env -> 'gpt-4o'. v0.3 introduces the two-tier
    convention so users can route cheap per-section work to a smaller model.
    """
    return (
        override
        or os.getenv("SKILL_ANYTHING_MODEL_FAST")
        or os.getenv("SKILL_ANYTHING_MODEL")
        or "gpt-4o"
    )


def resolve_smart_model(override: str | None = None) -> str:
    """Pick the 'smart' model for the global reduce step. See resolve_fast_model."""
    return (
        override
        or os.getenv("SKILL_ANYTHING_MODEL_SMART")
        or os.getenv("SKILL_ANYTHING_MODEL")
        or "gpt-4o"
    )


def cache_key(prompt: str, model: str, version: str = "v1") -> str:
    """Stable hash for (prompt, model, prompt-version) used as cache filename."""
    h = hashlib.sha256()
    h.update(version.encode())
    h.update(b"\0")
    h.update(model.encode())
    h.update(b"\0")
    h.update(prompt.encode("utf-8"))
    return h.hexdigest()[:16]


def _is_retryable_error(error: Exception) -> bool:
    """Avoid spending retries on deterministic client/request errors."""
    response = getattr(error, "response", None)
    status = getattr(response, "status_code", None)
    if isinstance(status, int) and 400 <= status < 500:
        return status in {408, 409, 425, 429}
    return True


class LLMCache:
    """JSON-per-call disk cache. One file per (prompt, model) hash."""

    def __init__(self, cache_dir: Path | None) -> None:
        self.dir = Path(cache_dir) if cache_dir else None
        if self.dir:
            self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def enabled(self) -> bool:
        return self.dir is not None

    def get(self, key: str) -> Any | None:
        if not self.enabled():
            return None
        path = self.dir / f"{key}.json"
        if not path.exists():
            with self._lock:
                self.misses += 1
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        with self._lock:
            self.hits += 1
        return data.get("value")

    def put(self, key: str, value: Any) -> None:
        if not self.enabled():
            return
        path = self.dir / f"{key}.json"
        temp_path = path.with_name(
            f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
        )
        try:
            payload = json.dumps({"value": value}, ensure_ascii=False, indent=2)
            with self._lock:
                temp_path.write_text(payload, encoding="utf-8")
                os.replace(temp_path, path)
        except Exception as e:
            log.debug("cache put failed for %s: %s", key, e)
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


def map_llm(
    items: list[T],
    fn: Callable[[T], R],
    *,
    concurrency: int = 4,
    cache: LLMCache | None = None,
    key_fn: Callable[[T], str] | None = None,
    label: str = "Processing",
    show_progress: bool = True,
    max_retries: int = 2,
) -> list[R | None]:
    """Run `fn` over `items` with bounded concurrency, disk cache, and retries.

    Returns results in the same order as `items`. Failed items become `None`
    after exhausting retries — callers should ``.filter(None)`` or check.

    Args:
        items: Inputs.
        fn: Per-item work (typically wraps an LLM call). Receives one item,
            returns a JSON-serialisable result.
        concurrency: Max in-flight calls. Defaults to 4 to stay friendly with
            free-tier rate limits. Bump via CLI/env on dedicated keys.
        cache: Optional LLMCache. When present and `key_fn` is given, results
            are written to / read from disk per item.
        key_fn: Returns a stable cache key for an item.
        label: Shown in the progress bar.
        show_progress: Set False in tests / non-tty environments.
        max_retries: Per-item retry budget after the first attempt.
    """
    if not items:
        return []

    results: list[R | None] = [None] * len(items)
    failed = 0

    progress_ctx = (
        Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            transient=True,
        )
        if show_progress
        else None
    )

    def worker(idx: int, item: T) -> tuple[int, R | None]:
        # Cache hit short-circuit.
        if cache is not None and key_fn is not None:
            key = key_fn(item)
            cached = cache.get(key)
            if cached is not None:
                return idx, cached

        last_err: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                value = fn(item)
                if value is None:
                    if attempt < max_retries:
                        time.sleep(min(2**attempt, 8))
                        continue
                    return idx, None
                if cache is not None and key_fn is not None and value is not None:
                    cache.put(key_fn(item), value)
                return idx, value
            except Exception as e:
                last_err = e
                if attempt < max_retries and _is_retryable_error(e):
                    # Exponential backoff: 1s, 2s, 4s ...
                    time.sleep(min(2**attempt, 8))
                else:
                    break
        log.warning("map_llm item %d failed after retries: %s", idx, last_err)
        return idx, None

    def execute() -> None:
        nonlocal failed
        task_id = None
        if progress_ctx is not None:
            task_id = progress_ctx.add_task(label, total=len(items))
        with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
            futures = [pool.submit(worker, i, item) for i, item in enumerate(items)]
            for fut in as_completed(futures):
                idx, value = fut.result()
                results[idx] = value
                if value is None:
                    failed += 1
                if progress_ctx is not None and task_id is not None:
                    progress_ctx.update(task_id, advance=1)

    if progress_ctx is not None:
        with progress_ctx:
            execute()
    else:
        execute()

    if failed:
        log.info("map_llm finished: %d/%d succeeded, %d failed",
                 len(items) - failed, len(items), failed)
    return results
