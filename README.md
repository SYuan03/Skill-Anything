<p align="center">
  <img src="assets/banner.png" alt="Skill-Anything" width="820" />
</p>

<h1 align="center">🔮 Skill-Anything: Turn Any Knowledge Source Into Interactive Skills</h1>

<p align="center">
  <b>Today's Knowledge Is Consumed Passively 📖. Skill-Anything Makes It Interactive 🧠.</b><br/>
  <b>Skill-Anything: Bridging the Gap Between Raw Content and Active Learning</b>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-22c55e?style=for-the-badge" alt="License"/></a>
  <a href="https://www.python.org"><img src="https://img.shields.io/badge/python-3.10+-3b82f6?style=for-the-badge" alt="Python"/></a>
  <a href="#-what-it-produces"><img src="https://img.shields.io/badge/outputs-12_types-f59e0b?style=for-the-badge" alt="12 Output Types"/></a>
  <a href="#-quiz--assessment"><img src="https://img.shields.io/badge/quiz-6_types-a855f7?style=for-the-badge" alt="6 Quiz Types"/></a>
</p>

<p align="center">
  <a href="#-quick-start">Quick Start</a> •
  <a href="#-what-it-produces">What It Produces</a> •
  <a href="#-demo">Demo</a> •
  <a href="#-when-to-use-skill-anything">Use Cases</a> •
  <a href="#-cli-reference">CLI</a> •
  <a href="#-python-api">API</a>
</p>

<p align="center">
  <b>One Command</b>: Turn any PDF, video, webpage, or text into a complete, interactive learning package — <br/>ready for self-study, team training, or integration with <a href="https://github.com/openclaw/openclaw">OpenClaw</a>, <a href="https://github.com/HKUDS/nanobot">nanobot</a>, and more.
</p>

---

## 🎯 Demo

<p align="center">
  <img src="assets/demo.gif" alt="Skill-Anything Demo" width="780" />
</p>

<p align="center">
  <a href="assets/demo.html">▶ Open interactive demo in browser</a>
</p>

---

## 🤔 Why Skill-Anything?

### The Knowledge Retention Gap

AI agents are getting smarter, but **humans still learn the same broken way** — read, forget, re-read, forget again. Research shows passive consumption retains **~10%** of information. Active recall (quizzes, flashcards, spaced repetition) pushes retention to **80%+**. But creating those materials manually? Nobody has time.

**Skill-Anything automates the entire pipeline.** One command. Any source. Production-ready learning package.

| **Current Pain Point** | **Skill-Anything's Fix** |
|:----|:----|
| 📖 **Passive reading** — read once, forget in a week | **12-section study guide** auto-generated with structured notes, cheat sheet, and concept map |
| 🧠 **No active recall** — no quizzes, no testing | **6 quiz types** (MCQ, scenario, comparison, ...) with explanations and A-F grading |
| 🃏 **No spaced repetition** — no flashcards, no review | **Auto-generated flashcards** with multi-round CLI review mode |
| ✍️ **Manual note-taking** — hours of summarizing | **AI-powered knowledge extraction** — glossary, key concepts, takeaways in seconds |
| 🤷 **No learning path** — what to study next? | **Prerequisites + next steps + recommended resources** auto-generated |
| 📄 **Source-locked** — knowledge stuck in one format | **Any source → structured YAML** — reusable across tools and workflows |

---

## 💡 Skill-Anything's Vision

<table>
<tr>
<td width="33%" align="center">
<h3>🌐 Universal Knowledge Extraction</h3>
<p>Every piece of content — PDF, video, webpage, or text — should be instantly convertible into structured, interactive learning materials. No manual effort, no friction.</p>
</td>
<td width="33%" align="center">
<h3>🧠 Active Learning by Default</h3>
<p>Learning should never be passive. Every knowledge source automatically becomes quizzable, reviewable, and practicable — with difficulty adaptation and progress tracking.</p>
</td>
<td width="33%" align="center">
<h3>🔗 Agent-Ready Knowledge</h3>
<p>Structured YAML output integrates seamlessly with AI agent ecosystems — <a href="https://github.com/openclaw/openclaw">OpenClaw</a> skills, <a href="https://github.com/HKUDS/nanobot">nanobot</a> tasks, <a href="https://github.com/HKUDS/LightRAG">LightRAG</a> knowledge bases, and more.</p>
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
# Edit .env — set your API key and model
```

Works with **any OpenAI-compatible API**:

| Provider | `API_BASE` |
|:---------|:-----------|
| OpenAI | `https://api.openai.com/v1` |
| DeepSeek | `https://api.deepseek.com/v1` |
| Qwen (Dashscope) | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| Ollama (local) | `http://localhost:11434/v1` |
| Any compatible API | Just set the base URL |

> **No API key?** Skill-Anything still works — falls back to rule-based generation. All features function, just lower quality.

### 3️⃣ Generate a Skill Pack

```bash
sa pdf textbook.pdf                                    # PDF → Skill
sa video https://www.youtube.com/watch?v=dQw4w9WgXcQ   # Video → Skill
sa web https://example.com/article                     # Webpage → Skill
sa text notes.md                                       # Text → Skill
sa auto anything                                       # Auto-detect
```

### 4️⃣ Learn Interactively

```bash
sa quiz output/my-skill.yaml       # Interactive quiz (6 types, graded A-F)
sa review output/my-skill.yaml     # Flashcard review (multi-round)
sa info output/my-skill.yaml       # View full skill pack details
```

---

## 📦 What It Produces

Every source generates **3 output files**:

```
output/
├── my-skill.yaml              # Structured data (quiz/review commands use this)
├── my-skill.md                # Complete study guide (read directly)
└── my-skill-concept-map.png   # AI-generated visual concept map
```

The study guide contains **12 sections** — a complete, self-contained learning package:

| # | Section | What You Get |
|:-:|:--------|:-------------|
| 1 | 📋 **Summary** | Core thesis, methodology, and conclusions — not a surface-level rehash |
| 2 | 🖼️ **Concept Map** | AI-generated visual diagram showing how concepts relate |
| 3 | 📍 **Outline** | Timestamped structure (video), page map (PDF), or section breakdown |
| 4 | 📖 **Detailed Notes** | Hierarchical, thorough notes — read these instead of the source |
| 5 | 🎯 **Key Concepts** | 10-15 core ideas, ordered foundational → advanced |
| 6 | 📘 **Glossary** | 15-25 domain terms with precise definitions + cross-references |
| 7 | ⚡ **Cheat Sheet** | One-page quick reference — print it, pin it to your wall |
| 8 | ✅ **Takeaways** | Actionable next steps — what to *do* with this knowledge |
| 9 | 📝 **Quiz** | 20-40 questions across 6 cognitive levels |
| 10 | 🃏 **Flashcards** | 25-50 spaced-repetition cards for long-term retention |
| 11 | 🔧 **Exercises** | Hands-on tasks: analysis, design, implementation, critique |
| 12 | 🗺️ **Learning Path** | Prerequisites + next steps + recommended books, courses, and tools |

---

## 🔧 When to Use Skill-Anything

| Category | Use Case | Source |
|:---------|:---------|:-------|
| 🎓 **Self-Study** | Turn any textbook, paper, or tutorial into an interactive study pack | PDF, Text |
| 🎬 **Video Learning** | Convert YouTube lectures, conference talks, or courses into quizzable notes | Video URL |
| 📰 **Research & Reading** | Extract structured knowledge from blog posts, documentation, or articles | Webpage |
| 👥 **Team Training** | Generate onboarding quizzes and review materials from internal docs | PDF, Text |
| 🤖 **Agent Knowledge** | Produce structured YAML for AI agents to query and reason over | Any |
| 📚 **Exam Prep** | Auto-generate practice tests from study materials | PDF, Text |
| 🔄 **Content Repurposing** | Turn long-form content into flashcards, cheat sheets, and exercises | Any |
| 🧪 **Teaching & Instruction** | Create assessment materials from lesson plans or lecture notes | Text, PDF |

---

## ✨ Key Features

### 🎮 Quiz & Assessment

**6 question types** designed to test different cognitive levels — from basic recall to applied reasoning:

| Type | Cognitive Level | Example |
|:-----|:----------------|:--------|
| **Multiple Choice** | Remember | "Which algorithm does X?" (4 options, plausible distractors) |
| **True / False** | Understand | "Statement: X always implies Y" (precise claims) |
| **Fill in the Blank** | Remember | "The attention formula is softmax(QK^T / ___)" |
| **Short Answer** | Analyze | "Explain why X matters for Y" (2-3 sentence response) |
| **Scenario** | Apply | "You're building X with constraint Y. What approach?" |
| **Comparison** | Evaluate | "Compare method A vs B for task Z — trade-offs?" |

```
$ sa quiz output/transformer.yaml --difficulty hard --count 10

--- Q1/10 ---  HARD  (Scenario)

  You're designing a search engine where queries are short
  but documents are long. How would you adapt the standard
  Transformer attention for efficiency?

  Answer > Use cross-attention with query as Q, chunked docs as K/V...

  Reference answer: Apply asymmetric attention — short queries attend
  to long documents via cross-attention with linear-complexity
  approximations like Linformer or chunked processing...

  Did you get it right? (y/n) > y

╔═══════════════════════════════════╗
║  Score: 9/10 (90%)  Grade: A      ║
╚═══════════════════════════════════╝
```

### 🃏 Flashcard Review

Multi-round spaced repetition — cards you miss come back:

```
$ sa review output/transformer.yaml

  ┌──────────────────────────────────────────┐
  │  Why does the Transformer divide dot     │
  │  products by sqrt(d_k)?                  │
  │                      #attention #math    │
  └──────────────────────────────────────────┘

  Press Enter to reveal...

  ┌──────────────────────────────────────────┐
  │  Large dot products push softmax into    │
  │  regions with vanishing gradients.       │
  │  Scaling by sqrt(d_k) keeps variance    │
  │  stable regardless of dimensionality.    │
  └──────────────────────────────────────────┘

  y=got it  n=review  > y

  --- Round 1 complete: 23 mastered, 2 need review ---
  --- Starting Round 2 with 2 cards ---
```

---

## 📋 CLI Reference

| Command | Description | Example |
|:--------|:------------|:--------|
| `sa pdf <file>` | PDF / book → skill pack | `sa pdf textbook.pdf` |
| `sa video <src>` | YouTube URL or subtitle → skill pack | `sa video https://youtu.be/xxx` |
| `sa web <url>` | Webpage / article → skill pack | `sa web https://example.com/post` |
| `sa text <src>` | Text / Markdown → skill pack | `sa text notes.md` |
| `sa auto <src>` | Auto-detect source type | `sa auto paper.pdf` |
| `sa quiz <yaml>` | Interactive quiz (6 types, graded) | `sa quiz x.yaml -n 10 -d hard` |
| `sa review <yaml>` | Flashcard review (multi-round) | `sa review x.yaml -n 20` |
| `sa info <yaml>` | View skill pack details | `sa info x.yaml --json` |

**Common options:** `--title "..."` `--output ./dir` `--count N` `--difficulty easy|medium|hard` `--no-shuffle`

---

## 🐍 Python API

```python
from skill_anything import Engine

engine = Engine()

# === Generate from any source ===
pack = engine.from_pdf("textbook.pdf", title="ML Fundamentals")
pack = engine.from_video("https://youtube.com/watch?v=xxx")
pack = engine.from_web("https://example.com/article")
pack = engine.from_text("notes.md")
pack = engine.from_source("auto-detect.pdf")  # auto-detect

# === Write to disk ===
engine.write(pack, "./output")
# Creates: my-skill.yaml + my-skill.md + my-skill-concept-map.png

# === Load and inspect ===
pack = Engine.load("output/my-skill.yaml")
print(f"Concepts: {len(pack.key_concepts)}")
print(f"Glossary: {len(pack.glossary)} terms")
print(f"Quiz: {len(pack.quiz_questions)} questions")
print(f"Flashcards: {len(pack.flashcards)} cards")
print(f"Exercises: {len(pack.practice_exercises)} tasks")
```

---

## 🗺️ Roadmap

- [x] 4 source parsers (PDF, Video, Web, Text)
- [x] 5 generators (Knowledge, Quiz, Flashcard, Practice, Visual)
- [x] 12 output sections per skill pack
- [x] 6 quiz question types with detailed explanations
- [x] Interactive quiz with A-F grading
- [x] Flashcard review with multi-round repetition
- [x] AI-generated concept map images
- [x] Auto source type detection
- [x] Offline fallback (works without LLM)
- [ ] **Audio parser** — podcasts, lectures, audiobooks (via Whisper)
- [ ] **Image/OCR parser** — slides, handwritten notes, screenshots
- [ ] **SM-2 scheduler** — true spaced repetition with interval tracking
- [ ] **Web UI** — browser-based quiz and review interface
- [ ] **Export** — Anki `.apkg`, Quizlet, Notion, Obsidian
- [ ] **Progress tracking** — mastery curves and adaptive difficulty
- [ ] **OpenClaw skill integration** — auto-publish as discoverable agent skills
- [ ] **Collaborative packs** — share and remix community skill packs

---

## 📖 Related Projects

<table>
<tr>
<td align="center" width="25%">
<b>🐈 nanobot</b><br/>
<a href="https://github.com/HKUDS/nanobot">Ultra-Lightweight AI Assistant</a>
</td>
<td align="center" width="25%">
<b>⚡ LightRAG</b><br/>
<a href="https://github.com/HKUDS/LightRAG">Simple & Fast RAG</a>
</td>
<td align="center" width="25%">
<b>🔧 CLI-Anything</b><br/>
<a href="https://github.com/HKUDS/CLI-Anything">Agent-Native Software</a>
</td>
<td align="center" width="25%">
<b>📄 RAG-Anything</b><br/>
<a href="https://github.com/HKUDS/RAG-Anything">All-in-One Multimodal RAG</a>
</td>
</tr>
</table>

> **Where Skill-Anything fits:** CLI-Anything makes **software** agent-native. LightRAG makes **retrieval** agent-native. Skill-Anything makes **knowledge** agent-native — turning any content into structured, interactive learning materials that both humans and agents can consume.

---

<p align="center">
  <a href="LICENSE">MIT License</a> — free to use, modify, and distribute.
</p>

<p align="center">
  <b>Skill-Anything</b> — <em>Stop consuming. Start retaining.</em>
</p>

<p align="center">
  PDF • Video • Web • Text → Quiz • Flashcards • Notes • Exercises • Concept Map
</p>
