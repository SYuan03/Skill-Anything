#!/usr/bin/env python3
"""Run reproducible offline quality checks against representative inputs.

This is intentionally independent of an API key. It exercises parsing,
extractive fallbacks, strict auditing, YAML round-trips, and portable exports
for short, long, multilingual, and hostile-looking source text.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from skill_anything.engine import Engine
from skill_anything.validation import audit_pack


CASES = {
    "short": (
        "# Retry policy\n\nA retry policy uses exponential backoff for transient failures. "
        "Permanent client errors should fail immediately."
    ),
    "long-unheaded": " ".join(
        f"Marker {index}: component {index} owns a distinct reliability responsibility."
        for index in range(1, 260)
    ),
    "multilingual": (
        "# 缓存一致性\n\n写入缓存时应先写临时文件，再通过原子替换发布完整结果。"
        "读取方不应该观察到只写了一半的 JSON。"
    ),
    "hostile-markup": (
        "# Safe export\n\nLiteral text such as </script><script>alert('x')</script> must remain data. "
        "The offline site escapes source text before embedding it in HTML."
    ),
}


def main() -> int:
    # Empty values prevent a local .env from turning this deterministic smoke
    # test into a paid/networked run.
    os.environ["SKILL_ANYTHING_API_KEY"] = ""
    os.environ["OPENAI_API_KEY"] = ""

    results = []
    with tempfile.TemporaryDirectory(prefix="skill-anything-quality-") as tmp:
        root = Path(tmp)
        for name, source in CASES.items():
            case_dir = root / name
            engine = Engine(cache_enabled=False)
            pack = engine.from_text(source, title=name)
            engine.write(pack, case_dir, format="all")
            yaml_path = case_dir / f"{name}.yaml"
            loaded = Engine.load(str(yaml_path))
            report = audit_pack(loaded, strict=True)
            site = case_dir / f"{name}-site" / "index.html"
            page = site.read_text(encoding="utf-8")
            payload_text = page.split('id="pack-data" type="application/json">', 1)[1].split(
                "</script>", 1
            )[0]
            payload = json.loads(payload_text)
            case_ok = report.ok and payload["title"] == name
            results.append(
                {
                    "case": name,
                    "ok": case_ok,
                    "citation_coverage": report.metrics["citation_coverage"],
                    "questions": len(loaded.quiz_questions),
                    "flashcards": len(loaded.flashcards),
                    "exercises": len(loaded.practice_exercises),
                }
            )

    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if all(result["ok"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
