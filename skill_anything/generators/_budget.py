"""Per-section quota allocation for quiz / flashcard / practice generators.

v0.2 used hard caps (max_questions=40, max_cards=50) with per-chunk loops:
a 500-page book hit the cap on the first few chapters and silently produced
zero questions for everything after. v0.3 allocates a total budget across
all sections proportional to section size, with a per-section minimum so the
tail is never empty.
"""

from __future__ import annotations

from skill_anything.models import Section


def allocate_quota(
    sections: list[Section],
    total: int,
    *,
    min_per_section: int = 1,
) -> dict[str, int]:
    """Return {section_id: quota} summing to roughly `total`.

    - Every section gets at least `min_per_section` (or 0 if total is too small
      to give everyone the minimum).
    - Remaining budget is distributed by section.total_chars weight.

    The total may slightly under- or over-shoot `total` because of rounding;
    callers that want a hard cap should slice after generation.
    """
    if not sections or total <= 0:
        return {}

    n = len(sections)
    if total < n * min_per_section:
        # Not enough budget for everyone — split as evenly as possible without
        # the per-section minimum.
        base, extra = divmod(total, n)
        quotas = {}
        for i, s in enumerate(sections):
            quotas[s.id] = base + (1 if i < extra else 0)
        return quotas

    remaining = total - n * min_per_section
    quotas = {s.id: min_per_section for s in sections}

    total_chars = sum(max(1, s.total_chars) for s in sections)
    if remaining > 0 and total_chars > 0:
        # Largest-remainder allocation by char weight, deterministic.
        shares = []
        for s in sections:
            weight = max(1, s.total_chars) / total_chars
            shares.append((s.id, remaining * weight))
        # Floor each share, distribute the rounding remainder to the largest
        # fractional parts so we hit `remaining` exactly.
        floored = [(sid, int(share), share - int(share)) for sid, share in shares]
        allocated = sum(f for _, f, _ in floored)
        leftover = remaining - allocated
        # Sort by descending fractional part for the leftover distribution.
        for sid, base, _ in sorted(floored, key=lambda x: x[2], reverse=True):
            quotas[sid] += base
        # Hand out leftover one-by-one.
        for sid, _, _ in sorted(floored, key=lambda x: x[2], reverse=True):
            if leftover <= 0:
                break
            quotas[sid] += 1
            leftover -= 1

    return quotas
