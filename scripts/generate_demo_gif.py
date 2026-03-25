#!/usr/bin/env python3
"""Generate a high-quality terminal demo GIF for the README."""

from PIL import Image, ImageDraw, ImageFont
import os

# ── Config ──────────────────────────────────────────────────────
W, H = 960, 640
PAD_X, PAD_Y = 28, 20
TITLEBAR_H = 38
FONT_SIZE = 14
LINE_H = 22
MAX_VISIBLE_LINES = (H - TITLEBAR_H - PAD_Y * 2) // LINE_H

# Colors
BG        = (9, 9, 11)
SURFACE   = (17, 17, 19)
SURFACE2  = (24, 24, 27)
BORDER    = (39, 39, 42)
TEXT      = (250, 250, 250)
TEXT_DIM  = (161, 161, 170)
TEXT3     = (113, 113, 122)
CYAN      = (34, 211, 238)
PURPLE    = (167, 139, 250)
GREEN     = (74, 222, 128)
YELLOW    = (251, 191, 36)
RED       = (248, 113, 113)
DOT_R     = (239, 68, 68)
DOT_Y     = (234, 179, 8)
DOT_G     = (34, 197, 94)

FONT_REG  = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoSansMono-Regular.ttf", FONT_SIZE)
FONT_BOLD = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoSansMono-Bold.ttf", FONT_SIZE)
FONT_SM   = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoSansMono-Regular.ttf", 12)

# ── Line definitions ────────────────────────────────────────────
# Each line is a list of (text, color, bold) spans
# "CLEAR" is a special marker to clear the screen

SCENE_GEN = [
    [("$ ", CYAN, False), ("sa auto transformer-paper.pdf", TEXT, True)],
    [],
    [("  Skill-Anything v1.0.0", TEXT3, False)],
    [("  Auto-detecting source type: ", TEXT3, False), ("PDF", CYAN, True)],
    [],
    [("PARSE   ", TEXT3, False), ("Reading PDF...", CYAN, False), ("  10 pages", TEXT3, False)],
    [("PARSE   ", TEXT3, False), ("Extracting text...", CYAN, False), ("  28,473 chars", TEXT3, False)],
    [("PARSE   ", TEXT3, False), ("Chunking content...", CYAN, False), ("  8 chunks", TEXT3, False)],
    [],
    [("GENERATE", TEXT3, False), ("  Notes + glossary + cheat sheet + takeaways", PURPLE, False)],
    [("GENERATE", TEXT3, False), ("  Quiz questions (6 types)", PURPLE, False), ("  24 questions", TEXT3, False)],
    [("GENERATE", TEXT3, False), ("  Flashcards", PURPLE, False), ("              30 cards", TEXT3, False)],
    [("GENERATE", TEXT3, False), ("  Practice exercises", PURPLE, False), ("        6 tasks", TEXT3, False)],
    [("GENERATE", TEXT3, False), ("  Concept map image", PURPLE, False), ("         1024x1024", TEXT3, False)],
    [],
    [("  >>> Skill pack generated!", GREEN, True)],
    [],
    [("  Key Concepts  12   Glossary       18", CYAN, False)],
    [("  Quiz Questions 24   Flashcards     30", CYAN, False)],
    [("  Exercises      6   Cheat Sheet    OK", CYAN, False)],
    [("  Detailed Notes OK   Learning Path  OK", CYAN, False)],
    [],
    [("  output/", TEXT3, False)],
    [("    |-- ", TEXT3, False), ("transformer-learning-pack.yaml", GREEN, False), ("  <- data", TEXT3, False)],
    [("    |-- ", TEXT3, False), ("transformer-learning-pack.md", GREEN, False), ("    <- study guide", TEXT3, False)],
    [("    '-- ", TEXT3, False), ("transformer-...-concept-map.png", GREEN, False), (" <- concept map", TEXT3, False)],
]

SCENE_QUIZ = [
    [("$ ", CYAN, False), ("sa quiz output/transformer-learning-pack.yaml -d hard -n 5", TEXT, True)],
    [],
    [("  Loading: Transformer Learning Pack  |  5 hard questions", TEXT3, False)],
    [],
    [("  --- Q1/5 ---  ", TEXT3, False), ("HARD", YELLOW, True), ("  (Scenario)", TEXT3, False)],
    [],
    [("  You are building a document search system where queries", TEXT, True)],
    [("  are short but documents are very long (10K+ tokens).", TEXT, True)],
    [("  How would you adapt Transformer attention?", TEXT, True)],
    [],
    [("  Answer > ", CYAN, False), ("Cross-attention with chunked docs as K/V...", TEXT, True)],
    [("  >>> Correct!", GREEN, True)],
    [],
    [("  --- Q2/5 ---  ", TEXT3, False), ("HARD", YELLOW, True), ("  (Comparison)", TEXT3, False)],
    [],
    [("  Compare self-attention with Bahdanau's recurrent", TEXT, True)],
    [("  attention: parallelism, memory, long-range deps?", TEXT, True)],
    [],
    [("  Answer > ", CYAN, False), ("Self-attn: O(1) path, parallel, O(n^2) mem...", TEXT, True)],
    [("  >>> Correct!", GREEN, True)],
    [],
    [("  --- Q3/5 ---  ", TEXT3, False), ("HARD", YELLOW, True), ("  (Fill-in-the-Blank)", TEXT3, False)],
    [("  d_model=512, h=8 heads, so d_k = d_v = ___", TEXT, True)],
    [("  Answer > ", CYAN, False), ("64", TEXT, True)],
    [("  >>> Correct!  ", GREEN, True), ("d_k = 512 / 8 = 64", TEXT3, False)],
    [],
    [("  +=============================================+", GREEN, False)],
    [("  |  Score: 5/5 (100%)    Grade: A+             |", GREEN, True)],
    [("  +=============================================+", GREEN, False)],
]


def draw_titlebar(draw, title_text):
    draw.rectangle([0, 0, W, TITLEBAR_H], fill=SURFACE2)
    draw.line([0, TITLEBAR_H, W, TITLEBAR_H], fill=BORDER, width=1)
    dot_y = TITLEBAR_H // 2
    for i, color in enumerate([DOT_R, DOT_Y, DOT_G]):
        cx = 20 + i * 22
        draw.ellipse([cx-6, dot_y-6, cx+6, dot_y+6], fill=color)
    draw.text((90, dot_y - 7), title_text, fill=TEXT3, font=FONT_SM)


def draw_line_spans(draw, y, spans):
    x = PAD_X
    for text, color, bold in spans:
        font = FONT_BOLD if bold else FONT_REG
        draw.text((x, y), text, fill=color, font=font)
        bbox = font.getbbox(text)
        x += bbox[2] - bbox[0]
    return x


def render_frame(visible_lines, title_text="skill-anything", show_cursor=True):
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, W-1, H-1], outline=BORDER, width=1)
    draw.rectangle([1, 1, W-2, H-2], fill=SURFACE)
    draw_titlebar(draw, title_text)

    # Only show lines that fit (scroll if needed)
    if len(visible_lines) > MAX_VISIBLE_LINES:
        display_lines = visible_lines[-MAX_VISIBLE_LINES:]
    else:
        display_lines = visible_lines

    y = TITLEBAR_H + PAD_Y
    last_x = PAD_X
    for line_spans in display_lines:
        if not line_spans:
            y += LINE_H // 2
            continue
        last_x = draw_line_spans(draw, y, line_spans)
        y += LINE_H

    if show_cursor and display_lines:
        cursor_y = y - LINE_H + 3 if display_lines[-1] else y + 3
        draw.rectangle([last_x + 2, cursor_y, last_x + 10, cursor_y + LINE_H - 6], fill=CYAN)

    return img


def get_line_delay(line):
    if not line:
        return 100
    texts = [s[0] for s in line]
    joined = " ".join(texts)
    if "$" in joined:
        return 500
    if ">>>" in joined and ("Correct" in joined or "generated" in joined):
        return 400
    if "Score" in joined:
        return 1200
    if "====" in joined:
        return 150
    if "Answer >" in joined:
        return 500
    if "Q1/" in joined or "Q2/" in joined or "Q3/" in joined:
        return 350
    return 130


def generate_gif(output_path):
    frames = []
    durations = []

    # ── Scene 1: Generation pipeline ──
    lines_so_far = []
    # Initial empty frame
    frames.append(render_frame([[]]))
    durations.append(800)

    for line in SCENE_GEN:
        lines_so_far.append(line)
        frames.append(render_frame(lines_so_far))
        durations.append(get_line_delay(line))

    # Hold on final generation output
    frames.append(render_frame(lines_so_far, show_cursor=True))
    durations.append(2500)

    # ── Transition: clear screen ──
    frames.append(render_frame([[]]))
    durations.append(600)

    # ── Scene 2: Interactive quiz ──
    lines_so_far = []
    for line in SCENE_QUIZ:
        lines_so_far.append(line)
        frames.append(render_frame(lines_so_far))
        durations.append(get_line_delay(line))

    # Hold on final quiz score
    frames.append(render_frame(lines_so_far, show_cursor=True))
    durations.append(4000)

    # Save
    frames[0].save(
        output_path,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"GIF saved: {output_path}")
    print(f"  {len(frames)} frames, {sum(durations)/1000:.1f}s total, {size_mb:.1f} MB")


if __name__ == "__main__":
    generate_gif("/mnt/shared-storage-user/dingshengyuan/fork/Skill-Anything/assets/demo.gif")
