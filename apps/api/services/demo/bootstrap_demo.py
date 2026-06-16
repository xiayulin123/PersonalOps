"""Seed the read-only PersonalOps demo account with sample workspaces and data."""

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models import (
    ChatMetric,
    Conversation,
    File,
    GitHubLink,
    LifeCalendarEvent,
    LifeGoogleConnection,
    LifeInboxBrief,
    LifeOutlookConnection,
    Memory,
    Message,
    MessageFeedback,
    PromptLog,
    PromptPeriodStats,
    StudyConcept,
    StudyQuestion,
    StudyQuestionSet,
    StudyTestAttempt,
    User,
    Workspace,
)
from services.auth.passwords import hash_password
from services.demo.constants import (
    DEMO_GCS_BUNDLE_PREFIX,
    DEMO_USER_ID,
    DEMO_WORKSPACES,
    WS_CAREER,
    WS_CODE,
    WS_LIFE,
    WS_STUDY,
)
from services.storage import gcs_app_storage as gcs
from services.storage.conversation_export import export_conversation_to_gcs
from services.storage.file_storage import save_uploaded_file

logger = logging.getLogger(__name__)

_DEMO_DATA_ROOT = Path(__file__).resolve().parents[2] / "demo_data" / "files"

FILE_SPECS: tuple[tuple[str, str, str], ...] = (
    (WS_STUDY, "study/os-deadlock-notes.md", "os-deadlock-notes.md"),
    (WS_STUDY, "study/probability-basics.md", "probability-basics.md"),
    (WS_CODE, "code/readme-snippet.md", "readme-snippet.md"),
    (WS_LIFE, "life/personal-goals.md", "personal-goals.md"),
    (WS_CAREER, "career/resume-outline.md", "resume-outline.md"),
)


@dataclass
class DemoSeedResult:
    user_id: str
    email: str
    created_user: bool
    workspaces: int = 0
    files: int = 0
    conversations: int = 0
    indexed_files: int = 0
    gcs_bundle_prefix: str | None = None
    warnings: list[str] = field(default_factory=list)


async def _get_or_create_demo_user(db: AsyncSession) -> tuple[User, bool]:
    email = settings.demo_email.strip().lower()
    password = settings.demo_password.strip()
    if not email or len(password) < 8:
        raise ValueError("DEMO_EMAIL and DEMO_PASSWORD (min 8 chars) are required")

    by_id = await db.get(User, DEMO_USER_ID)
    by_email = await db.scalar(select(User).where(User.email == email))

    if by_email is not None and by_email.id != DEMO_USER_ID:
        await db.delete(by_email)
        await db.commit()

    if by_id is not None:
        by_id.email = email
        by_id.password_hash = hash_password(password)
        by_id.email_verified = True
        by_id.is_demo = True
        await db.commit()
        await db.refresh(by_id)
        return by_id, False

    user = User(
        id=DEMO_USER_ID,
        email=email,
        password_hash=hash_password(password),
        email_verified=True,
        is_demo=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user, True


async def _clear_demo_data(db: AsyncSession, user_id: str) -> None:
    demo_workspace_ids = [workspace_id for workspace_id, _, _ in DEMO_WORKSPACES]
    if not demo_workspace_ids:
        return

    conversation_ids = list(
        await db.scalars(
            select(Conversation.id).where(Conversation.workspace_id.in_(demo_workspace_ids))
        )
    )
    if conversation_ids:
        message_ids = list(
            await db.scalars(
                select(Message.id).where(Message.conversation_id.in_(conversation_ids))
            )
        )
        if message_ids:
            await db.execute(
                delete(MessageFeedback).where(MessageFeedback.message_id.in_(message_ids))
            )
        await db.execute(delete(Message).where(Message.conversation_id.in_(conversation_ids)))
        await db.execute(delete(Conversation).where(Conversation.id.in_(conversation_ids)))

    set_ids = list(
        await db.scalars(
            select(StudyQuestionSet.id).where(
                StudyQuestionSet.workspace_id.in_(demo_workspace_ids)
            )
        )
    )
    if set_ids:
        await db.execute(delete(StudyTestAttempt).where(StudyTestAttempt.set_id.in_(set_ids)))
        await db.execute(delete(StudyQuestion).where(StudyQuestion.set_id.in_(set_ids)))
        await db.execute(delete(StudyQuestionSet).where(StudyQuestionSet.id.in_(set_ids)))

    await db.execute(delete(StudyConcept).where(StudyConcept.workspace_id.in_(demo_workspace_ids)))
    await db.execute(delete(ChatMetric).where(ChatMetric.workspace_id.in_(demo_workspace_ids)))
    await db.execute(delete(Memory).where(Memory.workspace_id.in_(demo_workspace_ids)))
    await db.execute(delete(PromptLog).where(PromptLog.workspace_id.in_(demo_workspace_ids)))
    await db.execute(
        delete(PromptPeriodStats).where(
            PromptPeriodStats.workspace_id.in_(demo_workspace_ids)
        )
    )
    await db.execute(delete(File).where(File.workspace_id.in_(demo_workspace_ids)))
    await db.execute(
        delete(LifeCalendarEvent).where(LifeCalendarEvent.workspace_id.in_(demo_workspace_ids))
    )
    await db.execute(
        delete(LifeInboxBrief).where(LifeInboxBrief.workspace_id.in_(demo_workspace_ids))
    )
    await db.execute(
        delete(LifeOutlookConnection).where(
            LifeOutlookConnection.workspace_id.in_(demo_workspace_ids)
        )
    )
    await db.execute(
        delete(LifeGoogleConnection).where(
            LifeGoogleConnection.workspace_id.in_(demo_workspace_ids)
        )
    )
    await db.execute(delete(GitHubLink).where(GitHubLink.workspace_id.in_(demo_workspace_ids)))
    await db.execute(
        delete(Workspace).where(
            (Workspace.user_id == user_id) | Workspace.id.in_(demo_workspace_ids)
        )
    )
    await db.commit()


async def _seed_workspaces(db: AsyncSession, user_id: str) -> dict[str, Workspace]:
    out: dict[str, Workspace] = {}
    for workspace_id, name, workspace_type in DEMO_WORKSPACES:
        record = Workspace(
            id=workspace_id,
            name=name,
            type=workspace_type,
            user_id=user_id,
            chat_mode="langgraph",
        )
        db.add(record)
        out[workspace_id] = record
    await db.commit()
    for record in out.values():
        await db.refresh(record)
    return out


async def _seed_files(
    db: AsyncSession,
    user_id: str,
    *,
    use_gcs: bool,
) -> dict[str, File]:
    seeded: dict[str, File] = {}
    gcs_ok = use_gcs and gcs.is_gcs_app_storage_enabled()

    for workspace_id, rel_path, filename in FILE_SPECS:
        source = _DEMO_DATA_ROOT / rel_path
        if not source.is_file():
            raise FileNotFoundError(f"Demo file missing: {source}")
        content = source.read_bytes()

        if gcs_ok:
            file_id, storage_backend, local_path, gcs_uri, size_bytes = save_uploaded_file(
                workspace_id=workspace_id,
                user_id=user_id,
                filename=filename,
                content=content,
            )
        else:
            workspace_dir = os.path.join(settings.uploads_dir, workspace_id)
            os.makedirs(workspace_dir, exist_ok=True)
            file_id = str(uuid.uuid4())
            local_path = os.path.join(workspace_dir, filename)
            with open(local_path, "wb") as handle:
                handle.write(content)
            storage_backend = "local"
            gcs_uri = None
            size_bytes = len(content)
        record = File(
            id=file_id,
            workspace_id=workspace_id,
            filename=filename,
            path=local_path,
            storage_backend=storage_backend,
            gcs_uri=gcs_uri,
            size_bytes=size_bytes,
            status="ready",
            chunk_count=12,
        )
        db.add(record)
        seeded[f"{workspace_id}:{filename}"] = record
    await db.commit()
    return seeded


async def _seed_memories(db: AsyncSession) -> None:
    specs = [
        (WS_STUDY, "language", "Bilingual explanations preferred", "memory"),
        (WS_STUDY, "exam_focus", "Midterm covers deadlock + scheduling", "memory"),
        (WS_CODE, "stack", "Python + TypeScript + FastAPI", "memory"),
        (WS_LIFE, "timezone", "America/Toronto", "memory"),
        (WS_CAREER, "target_role", "Software engineering intern — backend/platform", "memory"),
        (WS_CAREER, "skills", "Python, React, Docker, GCP, RAG pipelines", "skill"),
    ]
    for workspace_id, key, value, kind in specs:
        db.add(
            Memory(
                workspace_id=workspace_id,
                key=key,
                value=value,
                kind=kind,
                source="manual",
                status="active",
            )
        )
    await db.commit()


async def _seed_conversations(
    db: AsyncSession,
    user_id: str,
    files: dict[str, File],
    *,
    gcs_ok: bool = False,
) -> list[Conversation]:
    now = datetime.now(timezone.utc)
    study_file = files[f"{WS_STUDY}:os-deadlock-notes.md"]
    conv_specs = [
        (
            WS_STUDY,
            "Deadlock review",
            [
                ("user", "What are the four deadlock conditions?", None),
                (
                    "assistant",
                    "The four conditions are mutual exclusion, hold and wait, no preemption, "
                    "and circular wait. All four must hold simultaneously for deadlock.",
                    [
                        {
                            "filename": study_file.filename,
                            "page": 1,
                            "snippet": "Deadlock occurs when four conditions hold",
                        }
                    ],
                ),
            ],
        ),
        (
            WS_CODE,
            "API architecture",
            [
                ("user", "How is the PersonalOps API structured?", None),
                (
                    "assistant",
                    "Routers handle HTTP, services contain business logic, and Chroma stores "
                    "embeddings for file search.",
                    None,
                ),
            ],
        ),
        (
            WS_LIFE,
            "Weekly planning",
            [
                ("user", "Summarize my personal goals file.", None),
                (
                    "assistant",
                    "Your goals include exercise 3x/week, CE457A review, internship applications, "
                    "and Sunday meal prep.",
                    None,
                ),
            ],
        ),
        (
            WS_CAREER,
            "Resume polish",
            [
                ("user", "What skills should I highlight for backend internships?", None),
                (
                    "assistant",
                    "Highlight Python, FastAPI, Docker, cloud deploy experience, and your "
                    "PersonalOps RAG project with concrete outcomes.",
                    None,
                ),
            ],
        ),
    ]

    conversations: list[Conversation] = []
    for workspace_id, title, messages in conv_specs:
        conversation = Conversation(workspace_id=workspace_id, title=title)
        db.add(conversation)
        await db.flush()
        assistant_message_id: str | None = None
        for index, (role, content, sources) in enumerate(messages):
            message = Message(
                conversation_id=conversation.id,
                role=role,
                content=content,
                sources_json=json.dumps(sources) if sources else None,
                created_at=now - timedelta(minutes=len(messages) - index),
            )
            db.add(message)
            await db.flush()
            if role == "assistant":
                assistant_message_id = message.id
        if assistant_message_id and workspace_id == WS_STUDY:
            db.add(MessageFeedback(message_id=assistant_message_id, rating=1))
        conversations.append(conversation)

        db.add(
            ChatMetric(
                workspace_id=workspace_id,
                route="langgraph",
                latency_ms=840 + len(messages) * 120,
                file_source_count=1 if workspace_id == WS_STUDY else 0,
                web_source_count=0,
                had_trace=True,
            )
        )
    await db.commit()
    for conversation in conversations:
        await db.refresh(conversation)
        if gcs_ok:
            try:
                await export_conversation_to_gcs(
                    user_id=user_id,
                    workspace_id=conversation.workspace_id,
                    conversation_id=conversation.id,
                )
            except Exception as exc:
                logger.warning("Demo conversation GCS export failed: %s", exc)
    return conversations


async def _seed_study(db: AsyncSession, files: dict[str, File]) -> None:
    study_file = files[f"{WS_STUDY}:os-deadlock-notes.md"]
    sources = json.dumps(
        [{"filename": study_file.filename, "page": 1, "snippet": "Four deadlock conditions"}]
    )
    db.add(
        StudyConcept(
            workspace_id=WS_STUDY,
            title="Deadlock — four necessary conditions",
            summary="Deadlock needs mutual exclusion, hold-and-wait, no preemption, and circular wait.",
            key_points_json=json.dumps(
                [
                    "All four conditions must hold at once",
                    "Resource allocation graphs expose cycles",
                    "Prevention breaks at least one condition",
                ]
            ),
            example="Printer/scanner cycle between two processes.",
            sources_json=sources,
            mastery="reviewing",
            source_file_ids_json=json.dumps([study_file.id]),
        )
    )
    db.add(
        StudyConcept(
            workspace_id=WS_STUDY,
            title="Bayes' theorem",
            summary="Update beliefs with new evidence: P(A|B) = P(B|A)P(A)/P(B).",
            key_points_json=json.dumps(
                ["Identify prior and likelihood", "Normalize by total probability of evidence"]
            ),
            example="Rain vs cloudy sky calculation from lecture notes.",
            sources_json=json.dumps(
                [{"filename": "probability-basics.md", "page": 1, "snippet": "Bayes' theorem"}]
            ),
            mastery="learning",
            source_file_ids_json=json.dumps([]),
        )
    )

    practice_set = StudyQuestionSet(
        workspace_id=WS_STUDY,
        kind="practice",
        title="Week 5 practice",
        settings_json=json.dumps(
            {
                "type_counts": {"mcq": 1, "short_answer": 1, "calculation": 0, "true_false": 1},
                "difficulty": "medium",
            }
        ),
    )
    db.add(practice_set)
    await db.flush()

    db.add(
        StudyQuestion(
            set_id=practice_set.id,
            workspace_id=WS_STUDY,
            question_type="mcq",
            prompt="Which condition is NOT required for deadlock?",
            options_json=json.dumps(
                [
                    "Mutual exclusion",
                    "Preemption of resources",
                    "Hold and wait",
                    "Circular wait",
                ]
            ),
            correct_answer="Preemption of resources",
            explanation="Preemption prevents hold-and-wait deadlocks.",
            sources_json=sources,
            topic="Deadlock",
            sort_order=0,
        )
    )
    db.add(
        StudyQuestion(
            set_id=practice_set.id,
            workspace_id=WS_STUDY,
            question_type="true_false",
            prompt="Deadlock can occur even if only one condition is met.",
            options_json=json.dumps(["True", "False"]),
            correct_answer="False",
            explanation="All four conditions are necessary.",
            sources_json=sources,
            topic="Deadlock",
            sort_order=1,
        )
    )

    test_set = StudyQuestionSet(
        workspace_id=WS_STUDY,
        kind="test",
        title="Midterm drill",
        settings_json=json.dumps(
            {
                "type_counts": {"mcq": 1, "short_answer": 0, "calculation": 0, "true_false": 1},
                "time_limit_min": 30,
                "difficulty": "medium",
            }
        ),
    )
    db.add(test_set)
    await db.flush()

    mcq = StudyQuestion(
        set_id=test_set.id,
        workspace_id=WS_STUDY,
        question_type="mcq",
        prompt="In the Banker's algorithm, what does 'safe state' mean?",
        options_json=json.dumps(
            [
                "No process is waiting",
                "A safe sequence of allocations exists",
                "All resources are free",
                "Deadlock has already occurred",
            ]
        ),
        correct_answer="A safe sequence of allocations exists",
        explanation="Safety means some completion order avoids deadlock.",
        sources_json=sources,
        topic="Deadlock",
        sort_order=0,
    )
    tf = StudyQuestion(
        set_id=test_set.id,
        workspace_id=WS_STUDY,
        question_type="true_false",
        prompt="Circular wait can be broken by ordering resources.",
        options_json=json.dumps(["True", "False"]),
        correct_answer="True",
        explanation="Ordered acquisition prevents cycles.",
        sources_json=sources,
        topic="Deadlock",
        sort_order=1,
    )
    db.add(mcq)
    db.add(tf)
    await db.flush()

    attempt = StudyTestAttempt(
        workspace_id=WS_STUDY,
        set_id=test_set.id,
        answers_json=json.dumps({mcq.id: "A safe sequence of allocations exists", tf.id: "True"}),
        score_json=json.dumps(
            {"correct": 2, "total": 2, "auto_scored_correct": 2, "auto_scored_total": 2}
        ),
        submitted_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db.add(attempt)
    await db.commit()


async def _seed_life(db: AsyncSession) -> None:
    now = datetime.now(timezone.utc)
    db.add(
        LifeOutlookConnection(
            workspace_id=WS_LIFE,
            account_email="demo.outlook@personalops.live",
            enabled=True,
            last_mail_sync_at=now - timedelta(hours=2),
            last_calendar_sync_at=now - timedelta(hours=2),
        )
    )
    db.add(
        LifeGoogleConnection(
            workspace_id=WS_LIFE,
            account_email="demo.google@personalops.live",
            enabled=True,
            last_mail_sync_at=now - timedelta(hours=1),
            last_calendar_sync_at=now - timedelta(hours=1),
        )
    )
    inbox_specs = [
        ("Course registration opens Monday", "registrar@school.edu", "Reminder to enroll in CE457A."),
        ("Team sync — PersonalOps", "team@example.com", "Agenda: demo account polish and GCS seed."),
        ("Gym membership renewal", "billing@gym.com", "Your plan renews next week."),
    ]
    for index, (subject, sender, summary) in enumerate(inbox_specs):
        db.add(
            LifeInboxBrief(
                workspace_id=WS_LIFE,
                graph_message_id=f"demo-msg-{index}",
                provider="google" if index % 2 else "microsoft",
                subject=subject,
                from_address=sender,
                received_at=now - timedelta(hours=index + 1),
                body_preview=summary,
                summary=summary,
                summary_engine="preview",
            )
        )

    for day_offset, (subject, hour) in enumerate(
        [
            ("CE457A lecture", 10),
            ("PersonalOps standup", 14),
            ("Career office hours", 16),
        ]
    ):
        start = now.replace(hour=hour, minute=0, second=0, microsecond=0) + timedelta(
            days=day_offset + 1
        )
        db.add(
            LifeCalendarEvent(
                workspace_id=WS_LIFE,
                graph_event_id=f"demo-event-{day_offset}",
                provider="google",
                subject=subject,
                start_at=start,
                end_at=start + timedelta(hours=1),
                location="Campus / Zoom",
                synced_at=now,
            )
        )
    await db.commit()


async def _seed_code_career(db: AsyncSession) -> None:
    db.add(
        GitHubLink(
            workspace_id=WS_CODE,
            repo_url="https://github.com/example/personalops",
            default_branch="main",
            repo_full_name="example/personalops",
            repo_description="Demo linked repo for the code workspace.",
            last_synced_at=datetime.now(timezone.utc) - timedelta(days=2),
        )
    )
    await db.commit()


async def _seed_personalization(db: AsyncSession) -> None:
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    db.add(
        PromptLog(
            workspace_id=WS_STUDY,
            role="user",
            content="Explain deadlock prevention strategies from my notes.",
            chat_mode="langgraph",
            char_count=52,
            created_at=datetime.now(timezone.utc) - timedelta(days=2),
        )
    )
    db.add(
        PromptPeriodStats(
            workspace_id=WS_STUDY,
            period_type="weekly",
            period_start=week_start,
            prompt_count=12,
            distillation_status="completed",
            distilled_at=datetime.now(timezone.utc) - timedelta(days=1),
            summary_json=json.dumps(
                {
                    "themes": ["deadlock", "scheduling", "practice questions"],
                    "suggested_memory": "User prefers step-by-step OS explanations.",
                }
            ),
        )
    )
    await db.commit()


async def _index_demo_files(file_ids: list[str]) -> int:
    if not settings.openai_api_key.strip():
        return 0
    from routers.files import run_indexing

    indexed = 0
    for file_id in file_ids:
        try:
            await run_indexing(file_id)
            indexed += 1
        except Exception as exc:
            logger.warning("Demo indexing failed for %s: %s", file_id, exc)
    return indexed


def publish_demo_bundle_to_gcs(user_id: str) -> str | None:
    """Copy demo user's GCS prefix to system/demo-bundle for disaster recovery."""
    if not gcs.is_gcs_app_storage_enabled():
        return None
    return gcs.copy_prefix(
        source_prefix=gcs.user_prefix(user_id),
        dest_prefix=DEMO_GCS_BUNDLE_PREFIX,
    )


async def bootstrap_demo(
    db: AsyncSession,
    *,
    force: bool = False,
    index_files: bool = True,
    use_gcs: bool = False,
    publish_gcs_bundle: bool = False,
) -> DemoSeedResult:
    user, created = await _get_or_create_demo_user(db)
    warnings: list[str] = []

    if force:
        await _clear_demo_data(db, user.id)
    else:
        existing = await db.scalar(
            select(Workspace.id).where(Workspace.user_id == user.id).limit(1)
        )
        if existing is not None:
            return DemoSeedResult(
                user_id=user.id,
                email=user.email,
                created_user=created,
                workspaces=len(DEMO_WORKSPACES),
                warnings=["Demo data already present — use --force to rebuild."],
            )

    workspaces = await _seed_workspaces(db, user.id)
    files = await _seed_files(db, user.id, use_gcs=use_gcs)
    gcs_ok = use_gcs and gcs.is_gcs_app_storage_enabled()
    await _seed_memories(db)
    await _seed_conversations(db, user.id, files, gcs_ok=gcs_ok)
    await _seed_study(db, files)
    await _seed_life(db)
    await _seed_code_career(db)
    await _seed_personalization(db)

    indexed = 0
    if index_files:
        if settings.openai_api_key.strip():
            indexed = await _index_demo_files([record.id for record in files.values()])
        else:
            warnings.append("OPENAI_API_KEY not set — skipped file indexing (chat RAG limited).")

    bundle_prefix: str | None = None
    if publish_gcs_bundle:
        try:
            bundle_prefix = publish_demo_bundle_to_gcs(user.id)
        except Exception as exc:
            warnings.append(f"GCS bundle publish failed: {exc}")

    return DemoSeedResult(
        user_id=user.id,
        email=user.email,
        created_user=created,
        workspaces=len(workspaces),
        files=len(files),
        conversations=4,
        indexed_files=indexed,
        gcs_bundle_prefix=bundle_prefix,
        warnings=warnings,
    )
