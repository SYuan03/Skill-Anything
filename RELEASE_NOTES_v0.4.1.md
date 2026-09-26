# Skill-Anything v0.4.1 — Trust & Coverage

v0.4.1 is a reliability release. It makes generated learning material inspectable and prevents
large inputs from being silently under-covered.

## Verifiable source evidence

Quiz questions, flashcards, and exercises now request a short verbatim quote from the source.
Skill-Anything verifies that quote locally before accepting the item. Unsupported or invented
quotes are rejected; if an entire model response fails the gate, the generator uses a conservative
source-derived fallback.

Accepted citations are stored with the section, locator, chunk index, and quote. They are retained
when a YAML pack is loaded again and are shown in:

- Markdown study guides
- Offline interactive sites
- Anki exports
- `SKILL.md` asset YAML files

Knowledge-map calls must also provide verified quotes. These are displayed alongside the detailed
notes and retained in the pack's top-level `citations` collection.

## Complete long-section coverage

Earlier releases split documents into sections but still truncated an individual oversized section
to 5–6K characters. v0.4.1 groups all source chunks into bounded, ordered prompt windows, preserving
the tail of long chapters while keeping each model call manageable.

## Deterministic quality gate

The new audit command checks a saved pack without another model or network call:

```bash
sa audit output/my-pack.yaml --strict
sa audit output/my-pack.yaml --strict --json
```

It reports citation coverage, duplicate learning items, invalid multiple-choice options, missing
answers, missing explanations, and incomplete exercises. Strict mode exits non-zero when source
evidence is missing, so it can be used in CI or publishing workflows.

## Reliability fixes

- Model output is capped to the requested quota and duplicates are removed.
- Malformed JSON fields are normalised or rejected instead of leaking bad types downstream.
- Empty LLM responses use the existing retry budget.
- Cache writes are atomic, preventing concurrent readers from observing partial JSON.
- Inline text is represented as `<inline>` instead of being copied into public output metadata.
- Missing `.md`, `.txt`, `.rst`, and related text paths now fail clearly instead of treating the
  filename itself as lesson content.
- Offline practice prompts no longer invent unsupported real-world examples.

## Verification

- Grounding, adversarial-evidence, long-window, YAML round-trip, audit, exporter, parser, cache,
  and existing regression tests are included in the test suite.
- The full suite contains 102 passing tests in a clean Typer 0.27 environment.
- `python scripts/quality_smoke.py` exercises short, long-unheaded, multilingual, and
  hostile-markup sources through strict audit and every export format without an API key.
- Python 3.10, 3.11, and 3.12 byte-compilation is checked before release.
