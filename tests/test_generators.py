"""Tests for generators (offline/fallback mode)."""

import json

from skill_anything.generators.flashcard_gen import FlashcardGenerator
from skill_anything.generators.knowledge_gen import KnowledgeGenerator
from skill_anything.generators.practice_gen import PracticeGenerator
from skill_anything.generators.quiz_gen import QuizGenerator


def test_knowledge_gen_offline(sample_chunks):
    gen = KnowledgeGenerator()
    output = gen._generate_offline(sample_chunks)
    assert len(output.summary) > 0
    assert len(output.detailed_notes) > 0
    assert len(output.key_concepts) > 0


def test_knowledge_gen_timeline_offline(sample_chunks):
    timeline = KnowledgeGenerator._build_timeline_offline(sample_chunks)
    assert len(timeline) == 2
    assert timeline[0].title == "Chapter 1"


def test_quiz_gen_offline(sample_chunks):
    gen = QuizGenerator()
    questions = gen._generate_offline(sample_chunks, max_questions=10)
    assert len(questions) > 0
    for q in questions:
        assert q.question
        assert q.answer


def test_flashcard_gen_offline(sample_chunks):
    gen = FlashcardGenerator()
    cards = gen._generate_offline(sample_chunks, max_cards=10)
    assert len(cards) > 0
    for card in cards:
        assert card.front
        assert card.back


def test_practice_gen_offline(sample_chunks):
    gen = PracticeGenerator()
    exercises = gen._generate_offline(sample_chunks, max_exercises=5)
    assert len(exercises) > 0
    for ex in exercises:
        assert ex.title
        assert ex.description


def test_quiz_gen_parse_response():
    raw = json.dumps([
        {
            "question": "What is ML?",
            "type": "multiple_choice",
            "options": ["A. AI branch", "B. Art", "C. Music", "D. None"],
            "answer": "A. AI branch",
            "explanation": "ML is a branch of AI.",
            "difficulty": "easy",
        },
        {
            "question": "You have unlabeled data. How to proceed?",
            "type": "scenario",
            "answer": "Use unsupervised learning.",
            "explanation": "Without labels, clustering is appropriate.",
            "difficulty": "hard",
        },
    ])
    questions = QuizGenerator._parse_response(raw)
    assert len(questions) == 2
    assert questions[1].question_type.value == "scenario"


def test_practice_gen_parse_response():
    raw = json.dumps([{
        "title": "Design a System",
        "description": "Design a recommendation system.",
        "type": "design",
        "difficulty": "hard",
        "hints": ["Consider collaborative filtering"],
        "solution": "Use matrix factorization.",
    }])
    exercises = PracticeGenerator._parse_response(raw)
    assert len(exercises) == 1
    assert exercises[0].exercise_type == "design"


def test_flashcard_gen_parse_response():
    raw = json.dumps([
        {"front": "What?", "back": "Answer.", "tags": ["test"]},
        {"front": "How?", "back": "Like this.", "tags": []},
    ])
    cards = FlashcardGenerator._parse_response(raw)
    assert len(cards) == 2


def test_quiz_gen_handles_markdown_fences():
    raw = '```json\n[{"question": "Q?", "answer": "A", "type": "fill_blank", "difficulty": "hard"}]\n```'
    questions = QuizGenerator._parse_response(raw)
    assert len(questions) == 1


def test_knowledge_gen_parse_response():
    raw = json.dumps({
        "summary": "Test summary.",
        "detailed_notes": "## Section 1\n\nNotes here.",
        "key_concepts": ["Concept A: desc", "Concept B: desc"],
        "glossary": [{"term": "ML", "definition": "Machine Learning", "related_terms": ["AI"]}],
        "cheat_sheet": "| Term | Def |\n|---|---|\n| ML | Machine Learning |",
        "takeaways": ["Build a model", "Practice tuning"],
        "learning_path": {"prerequisites": ["Math"], "next_steps": ["DL"], "resources": ["Book"]},
    })
    output = KnowledgeGenerator._parse_response(raw, [])
    assert output.summary == "Test summary."
    assert len(output.glossary) == 1
    assert output.glossary[0].term == "ML"
    assert len(output.takeaways) == 2
    assert "Math" in output.learning_path.get("prerequisites", [])
