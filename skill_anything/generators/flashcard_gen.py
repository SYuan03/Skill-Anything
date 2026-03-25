"""Flashcard generator — create spaced-repetition flashcards from knowledge chunks."""

from __future__ import annotations

import json
import logging
import re

from skill_anything.models import Flashcard, KnowledgeChunk

log = logging.getLogger(__name__)

_FLASHCARD_PROMPT = """\
You are an expert in spaced-repetition learning design. Create {count} \
high-quality flashcards from the content below.

**Requirements:**
1. Front: A precise, unambiguous question or concept prompt
2. Back: A concise, complete answer (1-3 sentences max)
3. Tags: 2-3 relevant category tags
4. Cover the most important knowledge points in the content
5. Vary question styles: definitions, "why" questions, "how" questions, \
comparisons, and application prompts
6. Each card should test exactly one atomic piece of knowledge

Content:
{content}

Output ONLY a valid JSON array:

[
  {{
    "front": "What is ...?",
    "back": "... is a technique that ...",
    "tags": ["concept", "definition"]
  }}
]
"""


class FlashcardGenerator:
    """Generate flashcards from knowledge chunks using LLM."""

    def generate(
        self,
        chunks: list[KnowledgeChunk],
        *,
        count_per_chunk: int = 5,
        max_cards: int = 50,
    ) -> list[Flashcard]:
        try:
            from skill_anything.llm import chat, is_available

            if not is_available():
                return self._generate_offline(chunks, max_cards)
        except ImportError:
            return self._generate_offline(chunks, max_cards)

        cards: list[Flashcard] = []

        for chunk in chunks:
            if len(cards) >= max_cards:
                break

            remaining = min(count_per_chunk, max_cards - len(cards))
            prompt = _FLASHCARD_PROMPT.format(
                count=remaining,
                content=chunk.content[:3000],
            )

            raw = chat(
                [{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=4096,
            )

            if raw is None:
                continue

            parsed = self._parse_response(raw)
            for card in parsed:
                card.source_chunk = chunk.chunk_index
                cards.append(card)

        return cards[:max_cards]

    @staticmethod
    def _parse_response(raw: str) -> list[Flashcard]:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```\w*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group())
                except json.JSONDecodeError:
                    return []
            else:
                return []

        if not isinstance(data, list):
            return []

        cards: list[Flashcard] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            front = item.get("front", "")
            back = item.get("back", "")
            if front and back:
                cards.append(
                    Flashcard(
                        front=front,
                        back=back,
                        tags=item.get("tags", []),
                    )
                )

        return cards

    @staticmethod
    def _generate_offline(
        chunks: list[KnowledgeChunk], max_cards: int
    ) -> list[Flashcard]:
        """Fallback: extract key sentences as flashcards without LLM."""
        cards: list[Flashcard] = []

        for chunk in chunks:
            if len(cards) >= max_cards:
                break

            sentences = [s.strip() for s in re.split(r"[.!?]", chunk.content) if len(s.strip()) > 15]

            for sentence in sentences[:3]:
                if len(cards) >= max_cards:
                    break

                cards.append(
                    Flashcard(
                        front=f"Explain: {sentence[:60]}...",
                        back=sentence,
                        tags=[chunk.section] if chunk.section else [],
                        source_chunk=chunk.chunk_index,
                    )
                )

        return cards
