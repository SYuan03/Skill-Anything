<p align="center">
  <img src="assets/banner.png" alt="Skill-Anything" width="820" />
</p>

<h1 align="center">🔮 Skill-Anything: Turn Any Knowledge Source Into Interactive Skills</h1>

<p align="center">
  <b>PDF, Video, Webpage, Text — One Command → Complete Study Guide + Quiz + Flashcards + Exercises + Concept Map</b>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-22c55e?style=for-the-badge" alt="License"/></a>
  <a href="https://www.python.org"><img src="https://img.shields.io/badge/python-3.10+-3b82f6?style=for-the-badge" alt="Python"/></a>
  <a href="#-what-it-produces"><img src="https://img.shields.io/badge/outputs-12_types-f59e0b?style=for-the-badge" alt="12 Output Types"/></a>
  <a href="#-quiz-mode"><img src="https://img.shields.io/badge/quiz-6_types-a855f7?style=for-the-badge" alt="6 Quiz Types"/></a>
</p>

<p align="center">
  <a href="#-quick-start">Quick Start</a> •
  <a href="#-what-it-produces">What It Produces</a> •
  <a href="#-demo">Demo</a> •
  <a href="#-cli-reference">CLI</a> •
  <a href="#-python-api">Python API</a>
</p>

---

## 🎯 Demo

<p align="center">
  <img src="assets/demo.gif" alt="Skill-Anything Demo" width="780" />
</p>

> Try the [interactive version](assets/demo.html) in your browser for the full animated experience.

---

## 🤔 Why Skill-Anything?

<table>
<tr>
<td width="50%" align="center">
<h3>😴 Without Skill-Anything</h3>
<p>Read → Forget → Re-read → Still forget<br/>
Watch video → Take no notes → Gone in a week<br/>
Browse article → Bookmark → Never open again</p>
</td>
<td width="50%" align="center">
<h3>🚀 With Skill-Anything</h3>
<p>Read → One command → Complete study guide<br/>
Watch video → Quiz yourself → Actually learn<br/>
Browse article → Flashcard review → Long-term retention</p>
</td>
</tr>
</table>

---

## 🚀 Quick Start

### 1️⃣ Install

```bash
pip install skill-anything[all]
```

<details><summary><b>From source</b></summary>

```bash
git clone https://github.com/Skill-Anything/Skill-Anything.git
cd Skill-Anything && pip install -e ".[all,dev]"
```

</details>

### 2️⃣ Configure LLM

```bash
cp .env.example .env
# Edit .env with your API key
```

Works with any OpenAI-compatible API:

| Provider | `API_BASE` |
|:---------|:-----------|
| OpenAI | `https://api.openai.com/v1` |
| DeepSeek | `https://api.deepseek.com/v1` |
| Qwen | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| Ollama (local) | `http://localhost:11434/v1` |

> **No API key?** Still works — falls back to rule-based generation, just lower quality.

### 3️⃣ Generate

```bash
sa pdf textbook.pdf                                    # PDF → Skill
sa video https://www.youtube.com/watch?v=dQw4w9WgXcQ   # Video → Skill
sa web https://example.com/article                     # Web → Skill
sa text notes.md                                       # Text → Skill
sa auto anything                                       # Auto-detect
```

### 4️⃣ Learn

```bash
sa quiz output/my-skill.yaml       # Interactive quiz (6 types, graded A-F)
sa review output/my-skill.yaml     # Flashcard review (multi-round)
sa info output/my-skill.yaml       # View full details
```

---

## 📦 What It Produces

Every source generates **3 output files**:

```
output/
├── my-skill.yaml              # Structured data (used by quiz/review commands)
├── my-skill.md                # Complete study guide (read directly)
└── my-skill-concept-map.png   # AI-generated visual concept map
```

The study guide contains **12 sections**:

| # | Section | Description |
|:-:|:--------|:------------|
| 1 | 📋 **Summary** | Core thesis, methodology, conclusions — not a rehash |
| 2 | 🖼️ **Concept Map** | AI-generated visual diagram of concept relationships |
| 3 | 📍 **Outline** | Timeline (video), page map (PDF), or section structure |
| 4 | 📖 **Detailed Notes** | Hierarchical notes that replace re-reading the source |
| 5 | 🎯 **Key Concepts** | 10-15 core ideas, foundational → advanced |
| 6 | 📘 **Glossary** | 15-25 terms with definitions + cross-references |
| 7 | ⚡ **Cheat Sheet** | One-page quick reference — print it, pin it |
| 8 | ✅ **Takeaways** | Actionable steps: what to *do* with this knowledge |
| 9 | 📝 **Quiz** | 20-40 questions, 6 types (MCQ, T/F, fill, short, scenario, compare) |
| 10 | 🃏 **Flashcards** | 25-50 spaced-repetition cards |
| 11 | 🔧 **Exercises** | Hands-on tasks: analysis, design, implementation, critique |
| 12 | 🗺️ **Learning Path** | Prerequisites + next steps + recommended resources |

---

## 🎮 Quiz Mode

**6 question types** that test different cognitive levels:

| Type | Tests | Example |
|:-----|:------|:--------|
| **Multiple Choice** | Factual recall | "Which algorithm does X?" |
| **True / False** | Precision of understanding | "Statement: X always implies Y" |
| **Fill in the Blank** | Exact term recall | "The formula is softmax(QK^T / ___)" |
| **Short Answer** | Comprehension & synthesis | "Explain why X matters for Y" |
| **Scenario** | Application to real situations | "You're building X. What approach works best?" |
| **Comparison** | Analytical thinking | "Compare method A vs B for task Z" |

```
$ sa quiz output/transformer.yaml --difficulty hard --count 10

--- Q1/10 ---  HARD  (Scenario)

  You're designing a model for protein folding where
  distant residues interact. Why is self-attention
  particularly suited here?

  Answer > Self-attention connects all positions in O(1)...

  Reference answer: Self-attention allows direct interaction...
  Did you get it right? (y/n) > y

╔═══════════════════════════════════╗
║  Score: 9/10 (90%)  Grade: A      ║
╚═══════════════════════════════════╝
```

---

## 🃏 Flashcard Review

Multi-round spaced repetition — cards you miss come back in the next round:

```
$ sa review output/transformer.yaml

  ┌─────────────────────────────────────────┐
  │  What is the purpose of positional      │
  │  encoding in the Transformer?           │
  │                          #architecture  │
  └─────────────────────────────────────────┘

  Press Enter to reveal...

  ┌─────────────────────────────────────────┐
  │  Since the Transformer has no recurrence│
  │  positional encodings inject sequence   │
  │  order information into embeddings.     │
  └─────────────────────────────────────────┘

  y=got it  n=review  > y

╔═══════════════════════════════════╗
║  Mastered: 23  |  Need review: 2  ║
╚═══════════════════════════════════╝
```

---

## 📋 CLI Reference

| Command | Description | Example |
|:--------|:------------|:--------|
| `sa pdf <file>` | PDF / book → skill pack | `sa pdf textbook.pdf` |
| `sa video <src>` | Video / subtitle → skill pack | `sa video https://youtu.be/xxx` |
| `sa web <url>` | Webpage → skill pack | `sa web https://example.com/post` |
| `sa text <src>` | Text / Markdown → skill pack | `sa text notes.md` |
| `sa auto <src>` | Auto-detect and generate | `sa auto anything` |
| `sa quiz <yaml>` | Interactive quiz | `sa quiz x.yaml -n 10 -d hard` |
| `sa review <yaml>` | Flashcard review | `sa review x.yaml -n 20` |
| `sa info <yaml>` | View details | `sa info x.yaml --json` |

Options: `--title "..."`, `--output ./dir`, `--count N`, `--difficulty easy|medium|hard`, `--no-shuffle`

---

## 🐍 Python API

```python
from skill_anything import Engine

engine = Engine()

# Any source → SkillPack
pack = engine.from_pdf("textbook.pdf", title="ML Fundamentals")
pack = engine.from_video("https://youtube.com/watch?v=xxx")
pack = engine.from_web("https://example.com/article")
pack = engine.from_text("notes.md")
pack = engine.from_source("auto-detect.pdf")  # auto-detect

# Write: YAML + Markdown study guide + concept map image
engine.write(pack, "./output")

# Load and inspect
pack = Engine.load("output/my-skill.yaml")
print(f"{len(pack.quiz_questions)} questions, {len(pack.flashcards)} flashcards")
```

---

## 🗺️ Roadmap

- [x] 4 source parsers (PDF, Video, Web, Text)
- [x] 5 generators (Knowledge, Quiz, Flashcard, Practice, Visual)
- [x] 12 output sections per skill pack
- [x] 6 quiz question types with explanations
- [x] Interactive quiz with A-F grading
- [x] Flashcard review with multi-round repetition
- [x] AI-generated concept map images
- [x] Auto source type detection
- [x] Offline fallback (works without LLM)
- [ ] Audio parser (podcasts, lectures via Whisper)
- [ ] Image/OCR parser (slides, handwritten notes)
- [ ] SM-2 spaced repetition scheduler
- [ ] Web UI (browser-based quiz & review)
- [ ] Export to Anki, Quizlet, Notion, Obsidian
- [ ] Progress tracking + adaptive difficulty

---

<p align="center">
  <a href="LICENSE">MIT License</a>
</p>

<p align="center">
  <b>Skill-Anything</b> — <em>Stop consuming. Start retaining.</em>
</p>
