"""Study workspace LLM prompts (S1)."""

from __future__ import annotations

from services.study.schemas import StudyLanguage

CONCEPT_SYSTEM_PROMPT = """You are a study assistant for PersonalOps.
Generate review concept cards from the provided course material excerpts ONLY.

Rules:
- Use ONLY the provided context. If a concept is not supported, omit it.
- Do not invent definitions, formulas, or examples not grounded in the context.
- Each concept must include source_refs with filename and page from the context headers.
- Return valid JSON matching the schema exactly. No markdown fences.

Output JSON schema:
{
  "concepts": [
    {
      "title": "string",
      "summary": "string",
      "key_points": ["string", "..."],
      "example": "string or null",
      "source_refs": [{"filename": "string", "page": 1}]
    }
  ]
}"""

_LANGUAGE_INSTRUCTIONS: dict[StudyLanguage, str] = {
    "bilingual": (
        "Use clear Chinese with important technical terms kept in English "
        "(e.g. mutex, deadlock, scheduling)."
    ),
    "english": "Use English only.",
    "chinese": "Use Chinese only (Simplified Chinese).",
}


def _language_instruction(language: StudyLanguage) -> str:
    return _LANGUAGE_INSTRUCTIONS.get(language, _LANGUAGE_INSTRUCTIONS["bilingual"])


def build_concept_user_prompt(
    *,
    context_block: str,
    count: int,
    topic_hint: str | None,
    title_language: StudyLanguage,
    content_language: StudyLanguage,
) -> str:
    focus = (
        f"Focus on: {topic_hint.strip()}"
        if topic_hint and topic_hint.strip()
        else "Cover the most important exam-relevant concepts in the context."
    )
    title_note = _language_instruction(title_language)
    content_note = _language_instruction(content_language)
    return f"""Course material excerpts:

{context_block}

Task: Generate up to {count} distinct review concept cards.
{focus}

Language rules:
- Write each concept "title" field: {title_note}
- Write summary, key_points, and example fields: {content_note}

Return JSON with a "concepts" array. Omit weak or unsupported concepts rather than guessing."""


CONCEPT_JSON_RETRY_PROMPT = (
    "Your previous response was not valid JSON matching the schema. "
    'Return ONLY a JSON object: {"concepts": [...]} with no extra text.'
)

QUESTIONS_SYSTEM_PROMPT = """You are a study assistant for PersonalOps.
Generate practice exam questions from the provided course material excerpts ONLY.

Rules:
- Use ONLY the provided context. Do not invent facts.
- Match the requested difficulty and question types.
- For mcq: exactly 4 options, exactly one correct answer that matches one option text.
- For true_false: correct_answer must be "True" or "False".
- For short_answer: options must be null; correct_answer is a concise expected answer.
- For calculation: options must be null; prompt must include given numeric values from context.
  correct_answer is the final numeric result with units (e.g. "42.5 MPa" or "0.7143").
  correct_answer MUST match the final numeric result in the last solution_step exactly.
  solution_steps is REQUIRED: 3-8 numbered steps showing formula, substitution, and arithmetic.
  Base calculation questions on worked examples, formulas, and sample problems in the context.
- Include source_refs with filename and page from the context headers.
- Return valid JSON matching the schema. No markdown fences.

Output JSON schema:
{
  "questions": [
    {
      "question_type": "mcq|short_answer|true_false|calculation",
      "prompt": "string",
      "options": ["A", "B", "C", "D"] or null,
      "correct_answer": "string",
      "explanation": "string",
      "solution_steps": ["step 1 ...", "step 2 ..."] or [],
      "topic": "string or null",
      "source_refs": [{"filename": "string", "page": 1}]
    }
  ]
}"""


def build_questions_user_prompt(
    *,
    context_block: str,
    count: int,
    topic_hint: str | None,
    question_types: list[str],
    difficulty: str,
    content_language: StudyLanguage,
    exclude_prompts: list[str] | None = None,
) -> str:
    focus = (
        f"Focus on: {topic_hint.strip()}"
        if topic_hint and topic_hint.strip()
        else "Cover varied exam-relevant topics from the context."
    )
    types_label = ", ".join(question_types) if question_types else "mcq, short_answer"
    content_note = _language_instruction(content_language)
    calculation_note = ""
    if "calculation" in question_types:
        calculation_note = """
When generating calculation questions:
- Find formulas, worked examples, and numeric problems in the excerpts.
- State all given values in the prompt (with units).
- solution_steps must show: identify givens → write formula → substitute → compute → final answer with units.
- Do not skip algebra; each step should be one clear line a student can follow.
- If the context lacks enough numeric material for calculation, omit that question."""
    exclude_note = ""
    if exclude_prompts:
        previews = "\n".join(f"- {text[:180]}" for text in exclude_prompts[:6])
        exclude_note = f"""
Already generated (do NOT repeat or rephrase these prompts):
{previews}

Generate NEW questions on different scenarios, values, or sub-topics."""
    return f"""Course material excerpts:

{context_block}

Task: Generate exactly {count} distinct practice questions in the "questions" array when the context allows.
Difficulty: {difficulty}
Allowed question_type values: {types_label}
{focus}
{calculation_note}
{exclude_note}

Language: Write prompt, options, correct_answer, explanation, solution_steps, and topic using: {content_note}

Return JSON with a "questions" array. Target {count} separate questions; each must use a different scenario or sub-topic."""


QUESTIONS_JSON_RETRY_PROMPT = (
    "Your previous response was not valid JSON matching the schema. "
    'Return ONLY a JSON object: {"questions": [...]} with no extra text.'
)

TEST_SYSTEM_PROMPT = """You are a study assistant for PersonalOps.
Generate a formal practice EXAM from the provided course material excerpts ONLY.

Exam rules:
- Use ONLY the provided context. Do not invent facts.
- Questions must be exam-style: clear, unambiguous, and non-overlapping.
- Cover distinct topics; avoid duplicate concepts across questions.
- Match the requested difficulty and the single requested question type per batch.
- For mcq: exactly 4 options, exactly one correct answer matching one option.
- For true_false: correct_answer must be "True" or "False".
- For short_answer: options null; concise expected answer.
- For calculation: options null; include given values; solution_steps required (3-8 steps).
- Include source_refs with filename and page from context headers.
- Return valid JSON only. No markdown fences.

Output JSON schema:
{
  "questions": [
    {
      "question_type": "mcq|short_answer|true_false|calculation",
      "prompt": "string",
      "options": ["A", "B", "C", "D"] or null,
      "correct_answer": "string",
      "explanation": "string",
      "solution_steps": ["step 1 ..."] or [],
      "topic": "string or null",
      "source_refs": [{"filename": "string", "page": 1}]
    }
  ]
}"""
