#!/usr/bin/env python3
"""Generate a high-quality animated terminal demo GIF for Skill-Anything README."""

from PIL import Image, ImageDraw, ImageFont
import os

# ── Config ──
W, H = 1640, 1200  # 2x for retina clarity
BG = (13, 17, 23)
TITLE_BAR = (22, 27, 34)
DOT_R, DOT_Y, DOT_G = (255, 95, 87), (254, 188, 46), (40, 200, 64)
GREEN = (63, 185, 80)
WHITE = (230, 237, 243)
BLUE = (165, 214, 255)
PURPLE = (210, 168, 255)
ORANGE = (255, 166, 87)
DIM = (72, 79, 88)
YELLOW = (210, 153, 34)
CYAN = (57, 211, 83)

FONT_SIZE = 24
BOLD_SIZE = 24
LINE_H = 36
PAD_X = 40
PAD_Y = 80  # below title bar

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
BOLD_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"

font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
bold = ImageFont.truetype(BOLD_PATH, BOLD_SIZE)


def new_frame():
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    # Title bar
    draw.rounded_rectangle([0, 0, W, 64], radius=16, fill=TITLE_BAR)
    draw.rectangle([0, 48, W, 64], fill=TITLE_BAR)
    # Dots
    draw.ellipse([32, 20, 56, 44], fill=DOT_R)
    draw.ellipse([72, 20, 96, 44], fill=DOT_Y)
    draw.ellipse([112, 20, 136, 44], fill=DOT_G)
    # Title
    title = "skill-anything — ~/projects"
    bbox = draw.textbbox((0, 0), title, font=font)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2, 20), title, fill=DIM, font=font)
    return img, draw


def draw_colored_spans(draw, y, spans):
    """Draw a list of (text, color, is_bold) tuples on a line."""
    x = PAD_X
    for text, color, is_bold in spans:
        f = bold if is_bold else font
        draw.text((x, y), text, fill=color, font=f)
        bbox = draw.textbbox((0, 0), text, font=f)
        x += bbox[2] - bbox[0]


# ── Define all lines ──
# Each "scene" is a list of lines to show, built incrementally
# Line format: list of (text, color, bold) spans

SCENES = []

def line(spans):
    return spans

# Build the full script
all_lines = []

# -- Command 1 --
all_lines.append(line([("$ ", GREEN, True), ("sa auto ", WHITE, False), ("transformer.pdf", BLUE, False)]))

# -- Generation output --
all_lines.append(line([("[*] Source: ", DIM, False), ("transformer.pdf", ORANGE, False), ("  (PDF, 15 pages)", DIM, False)]))
all_lines.append(line([("[>] Extracting text...", DIM, False), ("  done", GREEN, False), ("  (12,847 chars)", DIM, False)]))
all_lines.append(line([("[>] Generating knowledge...", DIM, False), ("  done", GREEN, False)]))
all_lines.append(line([("[>] Generating quiz...", DIM, False), ("  32 questions", GREEN, False), ("  (6 types, 3 levels)", DIM, False)]))
all_lines.append(line([("[>] Generating flashcards...", DIM, False), ("  45 cards", GREEN, False)]))
all_lines.append(line([("[>] Generating exercises...", DIM, False), ("  8 tasks", GREEN, False)]))

# -- Output tree --
all_lines.append(line([("[+] Output written:", GREEN, True)]))
all_lines.append(line([("   output/", PURPLE, True)]))
all_lines.append(line([("     \u251C\u2500 transformer.yaml", BLUE, False), ("     structured data", DIM, False)]))
all_lines.append(line([("     \u251C\u2500 transformer.md", BLUE, False), ("       12-section study guide", DIM, False)]))
all_lines.append(line([("     \u2514\u2500 transformer-concept-map.png", BLUE, False)]))

all_lines.append(line([("[+] Done in 8.3s", GREEN, True)]))

# -- blank line --
all_lines.append(line([("", DIM, False)]))

# -- Command 2 --
all_lines.append(line([("$ ", GREEN, True), ("sa quiz ", WHITE, False), ("output/transformer.yaml", BLUE, False), (" -d hard", PURPLE, False)]))

# -- Quiz output --
all_lines.append(line([("\u2500\u2500\u2500 Q1/5 \u2500\u2500\u2500  ", PURPLE, False), ("HARD", YELLOW, True), ("  (Scenario)", DIM, False)]))
all_lines.append(line([("", DIM, False)]))
all_lines.append(line([("  You're building a search engine where queries are", WHITE, True)]))
all_lines.append(line([("  short but documents are very long. How would you", WHITE, True)]))
all_lines.append(line([("  adapt the Transformer attention for efficiency?", WHITE, True)]))
all_lines.append(line([("", DIM, False)]))
all_lines.append(line([("  Answer \u25B8 ", CYAN, False), ("Use cross-attention with chunked docs...", WHITE, False)]))
all_lines.append(line([("", DIM, False)]))
all_lines.append(line([("  [OK] Correct! ", GREEN, True), ("Cross-attention + linear approximations", DIM, False)]))
all_lines.append(line([("", DIM, False)]))

# -- Score --
all_lines.append(line([("  \u2554", GREEN, False), ("\u2550" * 42, GREEN, False), ("\u2557", GREEN, False)]))
all_lines.append(line([("  \u2551  ", GREEN, False), ("Score: 4/5 (80%)", ORANGE, True), ("    ", WHITE, False), ("Grade: A", GREEN, True), ("         \u2551", GREEN, False)]))
all_lines.append(line([("  \u255A", GREEN, False), ("\u2550" * 42, GREEN, False), ("\u255D", GREEN, False)]))


# ── Generate frames ──
# Show lines incrementally, with different "typing" speeds
frames = []
durations = []

# Phase 1: command 1 (line 0) - show quickly
# Phase 2: generation lines (1-12) - one by one with delay
# Phase 3: blank + command 2 (13-14)
# Phase 4: quiz (15-end) - one by one

# Timing: which lines appear per frame
# frame_plan: list of (num_lines_to_show, duration_ms)
frame_plan = [
    (1, 600),    # $ sa auto transformer.pdf
    (2, 400),    # Source
    (3, 400),    # Extracting
    (4, 500),    # Generating knowledge
    (5, 400),    # Generating quiz
    (6, 350),    # Generating flashcards
    (7, 350),    # Generating exercises
    (8, 500),    # Output written
    (9, 200),    # output/
    (10, 200),   # yaml
    (11, 200),   # md
    (12, 200),   # concept-map
    (13, 800),   # Done in 8.3s
    (14, 400),   # blank
    (15, 700),   # $ sa quiz
    (16, 500),   # --- Q1/5 ---
    (17, 100),   # blank
    (18, 300),   # question line 1
    (19, 300),   # question line 2
    (20, 400),   # question line 3
    (21, 300),   # blank
    (22, 800),   # Answer
    (23, 200),   # blank
    (24, 800),   # Correct
    (25, 200),   # blank
    (26, 300),   # box top
    (27, 300),   # score
    (29, 2500),  # box bottom (hold) - show all remaining lines
]

for num_lines, dur in frame_plan:
    img, draw = new_frame()
    for i in range(num_lines):
        if i < len(all_lines):
            y = PAD_Y + i * LINE_H
            draw_colored_spans(draw, y, all_lines[i])
    frames.append(img)
    durations.append(dur)

# Add a final "hold" frame (same as last) for 3 seconds then loop
frames.append(frames[-1].copy())
durations.append(3000)

# ── Save GIF ──
OUT = os.path.join(os.path.dirname(__file__), "demo-hq.gif")
frames[0].save(
    OUT,
    save_all=True,
    append_images=frames[1:],
    duration=durations,
    loop=0,
    optimize=True,
)

# Also save a half-size version for faster loading
frames_half = [f.resize((W // 2, H // 2), Image.LANCZOS) for f in frames]
OUT2 = os.path.join(os.path.dirname(__file__), "demo.gif")
frames_half[0].save(
    OUT2,
    save_all=True,
    append_images=frames_half[1:],
    duration=durations,
    loop=0,
    optimize=True,
)

print(f"Saved {OUT} ({os.path.getsize(OUT) // 1024} KB)")
print(f"Saved {OUT2} ({os.path.getsize(OUT2) // 1024} KB)")
