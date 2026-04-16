# Skill-Anything v0.2

## Highlights

v0.2 turns Skill-Anything from a source-to-study-pack generator into a lightweight repo-to-skill toolchain.

### New

- `sa repo <path-or-github-url>`
  - Generate onboarding-ready study packs from a local repository or a public GitHub repository
  - Uses a docs-first scan over README, docs, manifests/config, and a focused slice of key source files

- `sa import-skill <dir-or-skill-md>`
  - Import an existing `SKILL.md` package back into a reusable study pack
  - Rebuild YAML/study outputs and continue exporting with the normal workflow

- `sa lint <dir-or-skill-md>`
  - Validate skill packages before sharing or re-exporting
  - Fails on blocking packaging/data problems and keeps softer issues as warnings

### Improved

- `sa auto` now detects:
  - local repositories
  - public GitHub repository URLs
  - skill directories containing `SKILL.md`
  - direct `SKILL.md` files

- Python API now exposes:
  - `Engine.from_repo(...)`
  - `Engine.from_skill(...)`
  - `from skill_anything import Engine`

- README refreshed with:
  - a top-level `What's New in v0.2` section
  - repo/import/lint examples in Quick Start
  - updated CLI reference and FAQ

## Example Commands

```bash
sa repo . --format all
sa repo https://github.com/openai/openai-python --format study
sa import-skill ./output/my-skill --format study
sa lint ./output/my-skill
```

## Notes

- Repo support is designed for local repositories and public GitHub repositories.
- The repo pipeline is intentionally docs-first in v0.2 to stay fast and stable.
- `sa lint` uses an errors-fail, warnings-pass model so it works both locally and in CI.
