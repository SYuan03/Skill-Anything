"""Shared test fixtures for Skill-Anything."""

import pytest

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
)


@pytest.fixture
def sample_chunks() -> list[KnowledgeChunk]:
    return [
        KnowledgeChunk(
            content="Machine learning is a branch of artificial intelligence that enables "
            "computers to learn from data without being explicitly programmed. "
            "Supervised learning uses labeled training data to learn a mapping from "
            "inputs to outputs. Unsupervised learning discovers hidden patterns in "
            "unlabeled data.",
            section="Chapter 1",
            chunk_index=0,
            source_page=1,
        ),
        KnowledgeChunk(
            content="Deep learning is a subset of machine learning that uses multi-layer "
            "neural networks to learn hierarchical representations of data. "
            "Convolutional Neural Networks (CNNs) are particularly suited for image "
            "processing tasks. Recurrent Neural Networks (RNNs) handle sequential "
            "data like text and time series.",
            section="Chapter 2",
            chunk_index=1,
            source_page=5,
        ),
    ]


@pytest.fixture
def sample_pack() -> SkillPack:
    return SkillPack(
        title="Machine Learning Basics",
        source_type=SourceType.TEXT,
        source_ref="test.md",
        summary="A comprehensive overview of machine learning concepts.",
        detailed_notes="## Chapter 1\n\nML is a branch of AI...\n\n## Chapter 2\n\nDeep learning...",
        key_concepts=["Supervised Learning: uses labeled data",
                       "Unsupervised Learning: discovers patterns",
                       "Deep Learning: multi-layer neural networks"],
        glossary=[
            GlossaryEntry(term="CNN", definition="Convolutional Neural Network", related_terms=["DL", "CV"]),
            GlossaryEntry(term="RNN", definition="Recurrent Neural Network", related_terms=["NLP"]),
        ],
        timeline=[
            TimelineEntry(position="p.1", title="Introduction to ML", summary="Overview"),
            TimelineEntry(position="p.5", title="Deep Learning", summary="Neural networks"),
        ],
        cheat_sheet="| Algorithm | Type | Use Case |\n|-----------|------|----------|\n| CNN | DL | Images |",
        takeaways=["Start with supervised learning", "Use CNN for image tasks"],
        learning_path={
            "prerequisites": ["Linear Algebra", "Statistics"],
            "next_steps": ["NLP", "Computer Vision"],
            "resources": ["Deep Learning Book by Goodfellow"],
        },
        quiz_questions=[
            QuizQuestion(
                question="What is supervised learning?",
                options=["A. Learning with labels", "B. Learning without labels",
                         "C. Reinforcement learning", "D. None of the above"],
                answer="A. Learning with labels",
                explanation="Supervised learning uses labeled data.",
                difficulty=Difficulty.EASY,
                question_type=QuestionType.MULTIPLE_CHOICE,
            ),
            QuizQuestion(
                question="You have 10k unlabeled images. What approach would you use?",
                answer="Unsupervised learning (clustering) or self-supervised pre-training.",
                explanation="Without labels, supervised learning is not directly possible.",
                difficulty=Difficulty.HARD,
                question_type=QuestionType.SCENARIO,
            ),
        ],
        flashcards=[
            Flashcard(front="What is ML?", back="A branch of AI.", tags=["ML"]),
            Flashcard(front="What is CNN?", back="Convolutional Neural Network.", tags=["DL"]),
        ],
        practice_exercises=[
            PracticeExercise(
                title="Build a Simple Classifier",
                description="Implement a logistic regression classifier on the Iris dataset.",
                difficulty=Difficulty.MEDIUM,
                hints=["Use sklearn", "Split data 80/20"],
                solution="from sklearn.linear_model import LogisticRegression...",
                exercise_type="implementation",
            ),
        ],
    )
