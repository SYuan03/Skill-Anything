# Skill-Anything v0.4 — Share & Learn 🌈

## 📣 Highlights

v0.4 makes a generated study pack useful beyond the machine that created it. One command can
now produce a polished learning site that opens directly in a browser, works offline, and can
be sent as a ZIP. The same pack can also move into Anki without plugins or conversion scripts.

## New

### 🌐 Portable interactive learning sites

- `--format web` writes `<slug>-site/index.html`
- The app is a single HTML file with no CDN, tracking, build step, server, or runtime API call
- Includes searchable notes, concepts and glossary; revealable quizzes; flip cards; exercises;
  dark mode; print styling; JSON download; and browser-local learning progress
- Embedded content is JSON/script escaped before rendering to prevent source material from
  breaking out of the data block

### 📦 One-command sharing

```bash
sa share output/my-pack.yaml
```

This writes the offline site and `<slug>-site.zip`. Use `--no-zip` when only the directory is
needed. The directory is ready for GitHub Pages, Cloudflare Pages, Netlify, or any static host.

### 🧠 Anki interoperability

- `--format anki` writes `<slug>-anki.tsv`
- Both native flashcards and quiz questions become Anki notes
- Import metadata, HTML fields, topic tags, question type, and difficulty are included
- No `genanki` dependency or Anki add-on is required

### ✨ Complete `all` output

`--format all` now emits all four representations:

1. Structured YAML and Markdown study guide
2. Agent-compatible `SKILL.md` directory
3. Offline interactive web site
4. Anki-compatible TSV

## Fixed and improved

- LLM caches follow the CLI `--output` directory instead of always using `./output`
- Default concurrency is consistently 6 in the engine, CLI, README, and environment template
- Unknown output formats fail with a clear list of supported values
- Web- and Anki-only exports no longer attempt an unnecessary image-generation API call
- Typer's minimum version was raised to support modern Click releases and restore `--help`
- v0.3's FAST/SMART routing is now applied to actual API calls, not only cache keys and labels
- Long inline text no longer risks an OS `File name too long` error during automatic titling
- OpenAI-compatible chat can fall back to the core `httpx` client in constrained installs
- Reasoning-model requests omit unsupported custom temperature values (including GPT-5/6)
- Non-retryable HTTP 4xx errors no longer consume the retry budget and extra API calls
- Total API failure now falls back to usable offline content instead of silently writing an empty pack
- Output budgets now scale with source evidence, reducing cost, repetition, and hallucination on short notes
- `.env.example` now documents fast/smart model routing and concurrency

## Commands

```bash
sa export output/my-pack.yaml --format web
sa export output/my-pack.yaml --format anki
sa share output/my-pack.yaml
sa share output/my-pack.yaml --no-zip
sa repo . --format all
```

## Compatibility

- Existing YAML packs remain loadable; the `SkillPack` schema did not change
- Existing `study` and `skill` outputs retain their paths and contents
- `portal` is accepted as an alias for the `web` output format in the Python engine
- Python 3.10+ remains supported

## Validation

- 90 automated tests pass, including portability, injection safety, routing, fallback, adaptive
  budgets, and ZIP integrity coverage
- The wheel and source distribution build successfully as version `0.4.0`
- A live four-section run with `gpt-5.6-terra` generated every output format and passed Skill lint
- Independent model review scored grounding 9/10, coverage 10/10, educational usefulness 10/10,
  and portability 9/10, with no blocking issue
