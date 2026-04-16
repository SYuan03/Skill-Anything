"""Tests for data models."""

from skill_anything.models import (
    Difficulty,
    Flashcard,
    GlossaryEntry,
    KnowledgeChunk,
    PracticeExercise,
    QuestionType,
    QuizQuestion,
    SkillPack,
    SourceType,
    TimelineEntry,
    slugify,
)


def test_source_type_values():
    assert SourceType.PDF == "pdf"
    assert SourceType.VIDEO == "video"
    assert SourceType.WEBPAGE == "webpage"
    assert SourceType.TEXT == "text"
    assert SourceType.REPO == "repo"
    assert SourceType.SKILL == "skill"


def test_question_types():
    assert QuestionType.SCENARIO == "scenario"
    assert QuestionType.COMPARISON == "comparison"
    assert QuestionType.SHORT_ANSWER == "short_answer"


def test_knowledge_chunk_str():
    chunk = KnowledgeChunk(content="Hello world " * 20, section="Intro", chunk_index=0)
    s = str(chunk)
    assert "Intro" in s
    assert "..." in s


def test_glossary_entry():
    g = GlossaryEntry(term="ML", definition="Machine Learning", related_terms=["AI", "DL"])
    d = g.to_dict()
    assert d["term"] == "ML"
    assert len(d["related_terms"]) == 2


def test_timeline_entry():
    t = TimelineEntry(position="00:05:30", title="Intro", summary="Topic introduction")
    d = t.to_dict()
    assert d["position"] == "00:05:30"


def test_practice_exercise():
    e = PracticeExercise(
        title="Build X", description="Build something.", difficulty=Difficulty.HARD,
        hints=["hint1"], solution="solution", exercise_type="implementation",
    )
    d = e.to_dict()
    assert d["difficulty"] == "hard"
    assert d["type"] == "implementation"


def test_quiz_question():
    q = QuizQuestion(
        question="What is AI?",
        options=["A. Art", "B. Intelligence", "C. Automation", "D. None"],
        answer="B. Intelligence",
        difficulty=Difficulty.MEDIUM,
        question_type=QuestionType.MULTIPLE_CHOICE,
    )
    d = q.to_dict()
    assert d["type"] == "multiple_choice"
    assert len(d["options"]) == 4


def test_flashcard():
    f = Flashcard(front="Q?", back="A.", tags=["test"])
    assert f.to_dict()["tags"] == ["test"]


def test_skill_pack_to_dict(sample_pack: SkillPack):
    d = sample_pack.to_dict()
    assert d["title"] == "Machine Learning Basics"
    assert len(d["quiz_questions"]) == 2
    assert len(d["glossary"]) == 2
    assert len(d["practice_exercises"]) == 1
    assert "prerequisites" in d["learning_path"]


def test_skill_pack_stats(sample_pack: SkillPack):
    stats = sample_pack.stats
    assert stats["key_concepts"] == 3
    assert stats["glossary"] == 2
    assert stats["exercises"] == 1


def test_slugify():
    assert slugify("Hello World") == "hello-world"
    assert slugify("Machine Learning 101!") == "machine-learning-101"
    assert slugify("") == "skill-pack"
