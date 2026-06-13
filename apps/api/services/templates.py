from __future__ import annotations

from typing import TypedDict


class Template(TypedDict):
    id: str
    label: str
    description: str
    prompt: str


_COMMON_RULES = """
General rules:
- Retrieve and ground your answer in workspace files first when file search is available.
- Cite source filenames and page numbers whenever you rely on retrieved content.
- Follow workspace memory preferences for language, tone, and explanation style.
- Use clear Markdown structure with headings and numbered steps or lists.
- If retrieved context is insufficient, say what is missing instead of inventing details.
""".strip()


STUDY_TEMPLATES: list[Template] = [
    {
        "id": "summarize_lecture",
        "label": "Summarize lecture",
        "description": "Concise lecture summary with key concepts and citations.",
        "prompt": f"""Create a structured summary of the relevant lecture material in this workspace.

{_COMMON_RULES}

Output sections:
1. **Overview** — 2-3 sentences on the main topic
2. **Key concepts** — bullet list with brief explanations
3. **Important formulas / definitions** — if present in sources
4. **Study takeaways** — numbered list of what to remember for exams
""",
    },
    {
        "id": "study_guide",
        "label": "Generate study guide",
        "description": "Topic-by-topic guide from your uploaded notes.",
        "prompt": f"""Generate a study guide from the workspace materials.

{_COMMON_RULES}

Output sections:
1. **Topics covered** — list major themes found in sources
2. **Concept breakdown** — for each topic: definition, intuition, example
3. **Connections** — how topics relate to each other
4. **Review checklist** — numbered items the student should be able to explain
""",
    },
    {
        "id": "practice_quiz",
        "label": "Generate practice quiz",
        "description": "Practice questions grounded in your course files.",
        "prompt": f"""Generate a practice quiz based on workspace materials.

{_COMMON_RULES}

Output sections:
1. **Instructions** — how to use the quiz
2. **Questions** — 8-10 questions (mix of short answer and conceptual)
3. **Answer key** — concise answers with source citations where applicable
4. **Common mistakes** — 3 traps students often make on this material
""",
    },
    {
        "id": "exam_review_plan",
        "label": "7-day exam review plan",
        "description": "Day-by-day plan using your notes and focus areas.",
        "prompt": f"""Create a 7-day exam review plan based on workspace materials.

{_COMMON_RULES}

Output sections:
1. **Exam scope** — topics identified from sources
2. **7-day schedule** — Day 1 through Day 7 with specific tasks each day
3. **Daily goals** — what to read, practice, and self-test
4. **Priority topics** — rank by importance using source coverage and user notes
5. **Final day checklist** — last-minute review items
""",
    },
]

CODE_TEMPLATES: list[Template] = [
    {
        "id": "explain_codebase",
        "label": "Explain codebase structure",
        "description": "Architecture overview with file references.",
        "prompt": f"""Explain this project's codebase structure using workspace files.

{_COMMON_RULES}

Output sections:
1. **Project overview** — purpose and main components
2. **Directory map** — important folders and what they contain
3. **Key modules / services** — responsibilities and entry points
4. **Data flow** — how requests or jobs move through the system
5. **Where to start** — suggested reading order for a new contributor
""",
    },
    {
        "id": "debug_error",
        "label": "Debug error log",
        "description": "Analyze an error using logs and project context.",
        "prompt": f"""Help debug an error using workspace files and the user's notes.

{_COMMON_RULES}

Output sections:
1. **Error summary** — restate the problem clearly
2. **Likely causes** — ranked list with reasoning tied to project context
3. **Investigation steps** — numbered debugging steps to run
4. **Suggested fix** — concrete code or config changes if supported by sources
5. **Prevention** — how to avoid this class of error in the future
""",
    },
    {
        "id": "pr_summary",
        "label": "Generate PR summary",
        "description": "Draft a PR description from changes and README context.",
        "prompt": f"""Draft a pull request summary based on workspace materials and user notes.

{_COMMON_RULES}

Output sections:
1. **Summary** — what changed and why (2-4 sentences)
2. **Changes** — bullet list of main modifications
3. **Testing** — how the change was or should be verified
4. **Risks / rollout notes** — breaking changes, migrations, or follow-ups
5. **Reviewer focus** — what reviewers should pay attention to
""",
    },
]

LIFE_TEMPLATES: list[Template] = [
    {
        "id": "weekly_todos",
        "label": "Extract weekly todos",
        "description": "Pull actionable tasks from notes and personal documents.",
        "prompt": f"""Extract a weekly todo list from the workspace files and user notes.

{_COMMON_RULES}

Output sections:
1. **This week at a glance** — 2-3 sentence overview of priorities
2. **Todos by category** — group tasks (e.g. errands, health, admin, personal goals)
3. **Due dates / urgency** — mark items with deadlines or time sensitivity when found in sources
4. **Suggested order** — numbered sequence for tackling tasks this week
5. **Missing info** — what details are not in the files and should be clarified
""",
    },
    {
        "id": "deadline_finder",
        "label": "Find deadlines",
        "description": "Scan documents for dates, due dates, and appointments.",
        "prompt": f"""Find deadlines, appointments, and time-sensitive items in workspace files.

{_COMMON_RULES}

Output sections:
1. **Upcoming deadlines** — table or list: item, date/deadline, source file + page
2. **Recurring commitments** — weekly/monthly items if mentioned in sources
3. **Ambiguous dates** — items that need confirmation, with citations
4. **Recommended reminders** — what to calendar or follow up on first
""",
    },
    {
        "id": "action_plan",
        "label": "Generate action plan",
        "description": "Turn goals and notes into a step-by-step plan.",
        "prompt": f"""Create a practical action plan from workspace personal documents and notes.

{_COMMON_RULES}

Output sections:
1. **Goal summary** — what the user is trying to accomplish (from files/notes)
2. **Current situation** — relevant facts from sources
3. **Action steps** — numbered steps with clear owners and timeframes when possible
4. **Dependencies** — what must happen before each step
5. **First 3 actions** — what to do today or this week
""",
    },
    {
        "id": "document_summary",
        "label": "Summarize personal documents",
        "description": "Structured summary of uploaded life documents.",
        "prompt": f"""Summarize the personal documents in this workspace.

{_COMMON_RULES}

Output sections:
1. **Document overview** — what files were found and what they cover
2. **Key information** — bullet list of important facts, dates, and contacts
3. **Action items** — anything that requires follow-up
4. **Open questions** — gaps or unclear points that need user input
""",
    },
]

CAREER_TEMPLATES: list[Template] = [
    {
        "id": "resume_tailor",
        "label": "Tailor resume to job",
        "description": "Align resume bullets with a target role using your files.",
        "prompt": f"""Tailor the resume in workspace files toward the target role in user notes.

{_COMMON_RULES}

Output sections:
1. **Target role summary** — role and requirements inferred from notes/files
2. **Strong matches** — resume bullets or experiences that align well (with source citations)
3. **Gaps** — missing skills or experiences vs. the target role
4. **Suggested rewrites** — improved bullet points grounded in source material
5. **Keywords to add** — terms from job context that appear in sources or notes
""",
    },
    {
        "id": "jd_match",
        "label": "Match resume to job description",
        "description": "Compare resume against a job description with a fit score.",
        "prompt": f"""Compare the resume and job description materials in this workspace.

{_COMMON_RULES}

Output sections:
1. **Job requirements** — key requirements extracted from JD sources
2. **Match matrix** — requirement vs. resume evidence (met / partial / gap)
3. **Fit summary** — overall assessment in 2-4 sentences
4. **Top strengths** — best-aligned experiences with citations
5. **Improvement plan** — concrete steps to strengthen the application
""",
    },
    {
        "id": "cover_letter",
        "label": "Draft cover letter",
        "description": "Draft a cover letter grounded in resume and JD files.",
        "prompt": f"""Draft a cover letter using resume and job description materials in the workspace.

{_COMMON_RULES}

Output sections:
1. **Role and company context** — from files/notes
2. **Cover letter draft** — full letter text, professional tone per memory preferences
3. **Evidence mapping** — which resume points support each paragraph (with citations)
4. **Customization notes** — what the user should personalize before sending
""",
    },
    {
        "id": "interview_prep",
        "label": "Interview prep questions",
        "description": "Generate likely questions and answer outlines from your materials.",
        "prompt": f"""Prepare interview questions and answer outlines from workspace career files.

{_COMMON_RULES}

Output sections:
1. **Role focus** — target role and company context from sources
2. **Likely questions** — behavioral, technical, and role-specific (8-12 questions)
3. **Answer outlines** — bullet talking points tied to resume/source evidence
4. **Stories to prepare** — STAR-style examples drawn from cited experiences
5. **Questions to ask the interviewer** — 5 thoughtful questions
""",
    },
]


def get_templates(workspace_type: str) -> list[Template]:
    if workspace_type == "code":
        return CODE_TEMPLATES
    if workspace_type == "life":
        return LIFE_TEMPLATES
    if workspace_type == "career":
        return CAREER_TEMPLATES
    return STUDY_TEMPLATES


def get_template_by_id(workspace_type: str, template_id: str) -> Template | None:
    for template in get_templates(workspace_type):
        if template["id"] == template_id:
            return template
    return None


def build_template_message(template_prompt: str, user_message: str) -> str:
    notes = user_message.strip()
    if notes:
        return f"{template_prompt.strip()}\n\nUser notes:\n{notes}"
    return template_prompt.strip()
