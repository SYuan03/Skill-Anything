"""Visual generator — create concept map images via image generation API."""

from __future__ import annotations

import logging

from skill_anything.models import KnowledgeChunk

log = logging.getLogger(__name__)


class VisualGenerator:
    """Generate a visual concept map or diagram for the learning material."""

    def generate(
        self,
        title: str,
        key_concepts: list[str],
        chunks: list[KnowledgeChunk],
        *,
        output_path: str,
    ) -> str | None:
        """Generate a concept map image and save to output_path.

        Returns the file path on success, None on failure.
        """
        prompt = self._build_prompt(title, key_concepts, chunks)

        try:
            from skill_anything.llm import generate_image

            result = generate_image(prompt, output_path=output_path)
            if result:
                log.info("Generated concept map: %s", result)
            return result
        except Exception as e:
            log.warning("Visual generation failed: %s", e)
            return None

    @staticmethod
    def _build_prompt(
        title: str,
        key_concepts: list[str],
        chunks: list[KnowledgeChunk],
    ) -> str:
        concept_names = []
        for c in key_concepts[:8]:
            name = c.split(":")[0].strip() if ":" in c else c.strip()
            concept_names.append(name)

        concepts_str = ", ".join(concept_names) if concept_names else "key topics"

        return (
            f"A clean, professional concept map diagram for the topic '{title}'. "
            f"The diagram should show the relationships between these key concepts: "
            f"{concepts_str}. "
            f"Use a modern, minimal design with a white background. "
            f"Draw nodes as rounded rectangles with clear labels, connected by "
            f"arrows showing relationships. Use a consistent color palette "
            f"(blues, teals, and grays). The layout should flow from top to bottom "
            f"or left to right. No decorative elements — purely informational. "
            f"Text must be legible and in English."
        )
