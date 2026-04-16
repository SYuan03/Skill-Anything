#!/usr/bin/env python3
"""Generate a compact animated v0.2 README demo GIF."""

from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


W, H = 960, 620
BG = "#0b1020"
PANEL = "#11182d"
TITLE = "#151d31"
LINE = "#22304b"
WHITE = "#f8fafc"
SOFT = "#cbd5e1"
MUTED = "#94a3b8"
DIM = "#64748b"
GREEN = "#4ade80"
TEAL = "#67e8f9"
PURPLE = "#c4b5fd"
AMBER = "#fcd34d"

FONT_PATH = "/System/Library/Fonts/SFNSMono.ttf"
SANS_PATH = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"


def load_font(path: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


MONO = load_font(FONT_PATH, 15)
MONO_SMALL = load_font(FONT_PATH, 13)
MONO_MINI = load_font(FONT_PATH, 13)
SANS_BOLD = load_font(SANS_PATH, 18)
SANS = load_font(SANS_PATH, 14)
SANS_TITLE = load_font(SANS_PATH, 34)
SANS_SUB = load_font(SANS_PATH, 18)
SANS_CHIP = load_font(SANS_PATH, 13)


def text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
    x0, _, x1, _ = draw.textbbox((0, 0), text, font=font)
    return x1 - x0


def new_canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    draw.ellipse((40, 0, 280, 240), fill="#0f2a34")
    draw.ellipse((650, -20, 930, 260), fill="#1d203f")
    draw.ellipse((580, 380, 940, 760), fill="#2f260f")

    draw.text((72, 46), "Skill-Anything v0.2", fill=WHITE, font=SANS_TITLE)
    draw.text(
        (72, 88),
        "A tighter repo-to-skill loop: generate, re-import, validate, and re-export.",
        fill=MUTED,
        font=SANS_SUB,
    )

    draw.rounded_rectangle((56, 136, 904, 526), radius=22, fill=PANEL, outline="#24304d", width=1)
    draw.rounded_rectangle((56, 136, 904, 180), radius=22, fill=TITLE)
    draw.rectangle((56, 160, 904, 180), fill=TITLE)
    draw.ellipse((78, 152, 90, 164), fill="#fb7185")
    draw.ellipse((98, 152, 110, 164), fill="#fbbf24")
    draw.ellipse((118, 152, 130, 164), fill="#34d399")
    mid = "skill-anything  v0.2  demo"
    draw.text((W // 2 - text_width(draw, mid, MONO_MINI) // 2, 152), mid, fill="#8da2c0", font=MONO_MINI)

    draw.line((548, 196, 548, 494), fill=LINE, width=1)

    draw.rounded_rectangle((596, 206, 826, 330), radius=18, fill="#0c1326", outline="#23324f", width=1)
    draw.rounded_rectangle((596, 350, 826, 468), radius=18, fill="#0c1326", outline="#23324f", width=1)

    draw.text((620, 220), "What v0.2 adds", fill=WHITE, font=SANS_BOLD)
    chip(draw, (620, 254, 712, 282), "sa repo", "#0d2d31", "#1d8f88", "#5eead4")
    chip(draw, (726, 254, 806, 282), "import", "#232040", "#6d62d9", PURPLE, font=SANS_CHIP)
    chip(draw, (620, 294, 704, 322), "sa lint", "#2f260f", "#a17b18", AMBER)

    draw.text((620, 364), "Why it matters", fill=WHITE, font=SANS_BOLD)
    draw.text((620, 400), "Generate onboarding packs", fill="#5eead4", font=SANS)
    draw.text((620, 424), "Reuse external skills", fill=PURPLE, font=SANS)
    draw.text((620, 448), "Catch issues before sharing", fill=AMBER, font=SANS)

    pill(draw, (72, 554, 292, 588), "v0.2 mini demo")
    pill(draw, (306, 554, 552, 588), "generate -> import -> validate")
    draw.rounded_rectangle((566, 554, 888, 588), radius=17, fill="#3f3a2a")
    draw.text((727 - text_width(draw, "repo-to-skill toolchain", SANS) // 2, 562), "repo-to-skill toolchain", fill=WHITE, font=SANS)

    return img, draw


def pill(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str) -> None:
    draw.rounded_rectangle(box, radius=17, outline="#2b3a5b", width=1)
    x0, y0, x1, y1 = box
    draw.text(
        ((x0 + x1 - text_width(draw, text, SANS)) // 2, y0 + 8),
        text,
        fill=MUTED,
        font=SANS,
    )


def chip(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    text: str,
    fill: str,
    outline: str,
    color: str,
    font: ImageFont.ImageFont = SANS_CHIP,
) -> None:
    draw.rounded_rectangle(box, radius=10, fill=fill, outline=outline, width=1)
    x0, y0, x1, _ = box
    draw.text(((x0 + x1 - text_width(draw, text, font)) // 2, y0 + 6), text, fill=color, font=font)


def draw_line(draw: ImageDraw.ImageDraw, x: int, y: int, spans: list[tuple[str, str, ImageFont.ImageFont]]) -> None:
    cx = x
    for text, color, font in spans:
        draw.text((cx, y), text, fill=color, font=font)
        cx += text_width(draw, text, font)


LINES = [
    [("$ ", GREEN, MONO), ("sa repo ", WHITE, MONO), ("gh:openai/openai-python", SOFT, MONO)],
    [("[repo] ", MUTED, MONO_SMALL), ("scanned docs, built onboarding notes and glossary", SOFT, MONO_SMALL)],
    [("[pack] ", MUTED, MONO_SMALL), ("study_guide.md", TEAL, MONO_SMALL), ("  quiz.md  flashcards.md", DIM, MONO_SMALL)],
    [("        ", MUTED, MONO_SMALL), ("pack.yaml  skill/", DIM, MONO_SMALL)],
    [("$ ", GREEN, MONO), ("sa import-skill ", WHITE, MONO), ("./output/openai/skill", SOFT, MONO)],
    [("[import] ", MUTED, MONO_SMALL), ("restored frontmatter, refs, quiz assets, and YAML pack", SOFT, MONO_SMALL)],
    [("$ ", GREEN, MONO), ("sa lint ", WHITE, MONO), ("./output/openai/skill", SOFT, MONO)],
    [("[lint] ", MUTED, MONO_SMALL), ("0 errors", GREEN, MONO_SMALL), ("  2 warnings", AMBER, MONO_SMALL)],
]


def bottom_bar(draw: ImageDraw.ImageDraw) -> None:
    draw.rounded_rectangle((86, 462, 402, 502), radius=12, fill="#0f172a", outline="#1e293b", width=1)
    draw.text((108, 474), "output/openai/skill/SKILL.md", fill=SOFT, font=MONO_MINI)


def partial_line(spans: list[tuple[str, str, ImageFont.ImageFont]], visible_chars: int) -> list[tuple[str, str, ImageFont.ImageFont]]:
    remaining = visible_chars
    out: list[tuple[str, str, ImageFont.ImageFont]] = []
    for text, color, font in spans:
        if remaining <= 0:
            break
        segment = text[:remaining]
        if segment:
            out.append((segment, color, font))
        remaining -= len(segment)
    return out


def build_frames() -> tuple[list[Image.Image], list[int]]:
    frames: list[Image.Image] = []
    durations: list[int] = []

    def add_frame(render_fn, duration: int) -> None:
        img, draw = new_canvas()
        render_fn(draw)
        frames.append(img)
        durations.append(duration)

    y_positions = [202, 238, 268, 292, 338, 374, 416, 452]

    def render_until(draw: ImageDraw.ImageDraw, line_count: int, typed: int | None = None) -> None:
        for idx in range(line_count):
            spans = LINES[idx]
            if typed is not None and idx == line_count - 1:
                spans = partial_line(spans, typed)
            draw_line(draw, 86, y_positions[idx], spans)
        if line_count >= len(LINES):
            bottom_bar(draw)

    typing_targets = [len("".join(part for part, _, _ in LINES[i])) for i in (0, 3, 5)]

    add_frame(lambda d: render_until(d, 1, 10), 180)
    add_frame(lambda d: render_until(d, 1, 26), 180)
    add_frame(lambda d: render_until(d, 1, typing_targets[0]), 420)
    add_frame(lambda d: render_until(d, 2), 320)
    add_frame(lambda d: render_until(d, 3), 560)
    add_frame(lambda d: render_until(d, 4, 14), 180)
    add_frame(lambda d: render_until(d, 4, 38), 180)
    add_frame(lambda d: render_until(d, 4, typing_targets[1]), 360)
    add_frame(lambda d: render_until(d, 5), 520)
    add_frame(lambda d: render_until(d, 6, 8), 160)
    add_frame(lambda d: render_until(d, 6, typing_targets[2]), 320)
    add_frame(lambda d: render_until(d, 7), 560)
    add_frame(lambda d: render_until(d, 7) or bottom_bar(d), 1600)

    return frames, durations


def main() -> None:
    frames, durations = build_frames()
    assets = Path(__file__).resolve().parent
    out = assets / "v02-demo.gif"
    frames[0].save(
        out,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )
    print(f"saved {out} ({os.path.getsize(out) // 1024} KB)")


if __name__ == "__main__":
    main()
