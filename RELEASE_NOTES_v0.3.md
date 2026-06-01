# Skill-Anything v0.3

## Highlights

v0.3 makes Skill-Anything actually usable on **long sources** — books, multi-hour talks, large repos.

Previous versions silently degraded on anything past ~15K characters: the knowledge generator truncated input, quiz/flashcard generation hit hard per-call caps before reaching later chapters, and every LLM call was sequential with no caching. v0.3 introduces a section-aware, map-reduce pipeline with concurrency and a disk cache, so a 12-chapter book produces a study pack that actually covers every chapter.

### New

- **Section-aware parsing** across every source type
  - PDFs use the embedded outline (TOC) when available, with a page-range fallback
  - Text/Markdown splits by headings into structured sections
  - Web pages reuse heading detection for long articles
  - Video/audio bucket transcripts into 5-minute time sections with anchored timestamps
  - Repos produce one Section per selected file

- **Map-reduce knowledge generation**
  - Per-section "map" calls produce local summary / key concepts / glossary / notes
  - A single "reduce" call synthesizes a global summary, cheat sheet, takeaways, and learning path from the map outputs
  - `detailed_notes` is assembled deterministically from per-section notes — no truncation
  - Two-tier model routing: `SKILL_ANYTHING_MODEL_FAST` for map, `SKILL_ANYTHING_MODEL_SMART` for reduce

- **Per-section quota allocation** for quiz / flashcards / exercises
  - Largest-remainder weighting by section size, with a guaranteed minimum per section
  - Every chapter gets coverage even when the total budget is small

- **Concurrent LLM execution with a disk cache**
  - `ThreadPoolExecutor`-based map runner with rich progress bars
  - Per-section failure isolation: a single failed section doesn't sink the whole pack
  - Cache key = `sha256(prompt + model + version)`; second runs of the same source skip every cached call
  - Cache lives under `./output/.skill-anything/<slug>/` (gitignored)

- **New CLI flags** for every source command
  - `--concurrency` / `-c` to control parallel LLM calls (default 6)
  - `--no-cache` to bypass the disk cache for a clean run

- **New environment variables**
  - `SKILL_ANYTHING_MODEL_FAST` — fast/cheap tier for per-section map calls
  - `SKILL_ANYTHING_MODEL_SMART` — stronger tier for the global reduce call
  - Both fall back to `SKILL_ANYTHING_MODEL` when unset

### Improved

- **Repo parser** now uses a 240K-character budget split (docs 50% / manifest 15% / code 35%) instead of hard `[:12]+[:10]+[:8]` caps. Long repos surface meaningful code in addition to README/docs.
- **Practice exercises** no longer concatenate every chunk into a single prompt — each section gets its own call, so long sources don't fail with context overruns.
- **Engine.write()** no longer re-renders the concept map twice when `--format all` is used.
- **Quiz runner** removed an incorrect substring fallback that matched `A` inside `ABLE`.

## Case Study

A 12-chapter distributed-systems primer (~4.4KB / ~12 sections) processed end-to-end with `--concurrency 6`:

| Output | Count |
|:-------|:------|
| Outline entries | 13 |
| Key concepts | 15 |
| Glossary terms | 62 |
| Quiz questions | 30 |
| Flashcards | 40 |
| Exercises | 10 |
| Takeaways | 10 |

Chapter coverage verified by keyword matching across the generated quiz / flashcards / exercises: **every chapter (1–12) is represented**, including narrower topics like CRDTs, observability, and messaging semantics that v0.2 routinely dropped once the per-call cap was hit.

## Example Commands

```bash
# Long PDF with full concurrency and caching
sa pdf book.pdf --format all --concurrency 8

# Same source again — second run hits the cache and finishes in seconds
sa pdf book.pdf --format all --concurrency 8

# Bypass cache for a clean run
sa pdf book.pdf --no-cache

# Two-tier model routing via env
export SKILL_ANYTHING_MODEL_FAST=gpt-4o-mini
export SKILL_ANYTHING_MODEL_SMART=gpt-4o
sa repo . --format all
```

## Notes

- The cache directory `./output/.skill-anything/` is gitignored by default.
- `--concurrency` defaults to 6; raise it for IO-bound LLM endpoints with generous rate limits.
- The map-reduce pipeline is fully backward-compatible: existing `Parser.parse()` callers still receive a flat list of chunks via a shim, and `parse_sections()` is the new canonical entry point.
- All 75 tests pass (62 existing + 13 new v0.3 tests covering quota allocation, cache round-trip, failure isolation, concurrency caps, and per-chapter coverage).
