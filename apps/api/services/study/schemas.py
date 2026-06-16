"""Internal Pydantic models for Study workspace LLM output (S1)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LlmSourceRef(BaseModel):
    filename: str
    page: int = 1


class LlmConceptItem(BaseModel):
    title: str
    summary: str
    key_points: list[str] = Field(default_factory=list)
    example: str | None = None
    source_refs: list[LlmSourceRef] = Field(default_factory=list)


class LlmConceptsResponse(BaseModel):
    concepts: list[LlmConceptItem] = Field(default_factory=list)


class LlmQuestionItem(BaseModel):
    question_type: str
    prompt: str
    options: list[str] | None = None
    correct_answer: str
    explanation: str = ""
    solution_steps: list[str] = Field(default_factory=list)
    topic: str | None = None
    source_refs: list[LlmSourceRef] = Field(default_factory=list)


class LlmQuestionsResponse(BaseModel):
    questions: list[LlmQuestionItem] = Field(default_factory=list)


StudyLanguage = Literal["bilingual", "english", "chinese"]
StudyMastery = Literal["learning", "reviewing", "mastered"]
StudyQuestionType = Literal["mcq", "short_answer", "true_false", "calculation"]
StudyDifficulty = Literal["easy", "medium", "hard"]
StudyQuestionSetKind = Literal["practice", "test"]
