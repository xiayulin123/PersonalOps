import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


def _new_id() -> str:
    return str(uuid.uuid4())


DEFAULT_TOOL_SETTINGS_JSON = (
    '{"file_search": true, "web_search": false, "memory": true, "github_read": false, "code_search": false}'
)
DEFAULT_PERSONALIZATION_SETTINGS_JSON = "{}"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    email_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true", default=True
    )
    is_demo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    workspaces: Mapped[list["Workspace"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    api_credentials: Mapped[list["UserApiCredential"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class AuthEmailChallenge(Base):
    """Short-lived email codes for register verify and password reset."""

    __tablename__ = "auth_email_challenges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class UserApiCredential(Base):
    """Per-user API keys (B2) — encrypted at rest."""

    __tablename__ = "user_api_credentials"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    provider: Mapped[str] = mapped_column(String(32), primary_key=True)
    encrypted_secret: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="api_credentials")


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # "study" | "code" | "life" | "career"
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    tool_settings_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=DEFAULT_TOOL_SETTINGS_JSON,
    )
    chat_mode: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="langgraph",
    )  # "langgraph" | "cursor_agent"
    personalization_settings_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=DEFAULT_PERSONALIZATION_SETTINGS_JSON,
    )
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )

    user: Mapped["User | None"] = relationship(back_populates="workspaces")
    files: Mapped[list["File"]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )
    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )
    memories: Mapped[list["Memory"]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )
    github_link: Mapped["GitHubLink | None"] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
        uselist=False,
    )
    watch_folder: Mapped["WatchFolder | None"] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
        uselist=False,
    )
    life_outlook: Mapped["LifeOutlookConnection | None"] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
        uselist=False,
    )
    life_google: Mapped["LifeGoogleConnection | None"] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
        uselist=False,
    )
    life_inbox_briefs: Mapped[list["LifeInboxBrief"]] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    life_calendar_events: Mapped[list["LifeCalendarEvent"]] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    study_concepts: Mapped[list["StudyConcept"]] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    study_question_sets: Mapped[list["StudyQuestionSet"]] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
    )


class LifeOutlookConnection(Base):
    __tablename__ = "life_outlook_connections"

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        primary_key=True,
    )
    account_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_mail_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_calendar_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    workspace: Mapped["Workspace"] = relationship(back_populates="life_outlook")


class LifeGoogleConnection(Base):
    __tablename__ = "life_google_connections"

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        primary_key=True,
    )
    account_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_mail_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_calendar_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    workspace: Mapped["Workspace"] = relationship(back_populates="life_google")


class LifeInboxBrief(Base):
    __tablename__ = "life_inbox_briefs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    graph_message_id: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="microsoft")
    subject: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    from_address: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    from_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    body_preview: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary_engine: Mapped[str] = mapped_column(
        String(32), nullable=False, default="preview"
    )
    dismissed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    workspace: Mapped["Workspace"] = relationship(back_populates="life_inbox_briefs")


class LifeCalendarEvent(Base):
    __tablename__ = "life_calendar_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    graph_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="microsoft")
    subject: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    start_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    location: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_all_day: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    organizer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    workspace: Mapped["Workspace"] = relationship(back_populates="life_calendar_events")


class GitHubLink(Base):
    __tablename__ = "github_links"

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        primary_key=True,
    )
    repo_url: Mapped[str] = mapped_column(Text, nullable=False)
    default_branch: Mapped[str] = mapped_column(String(128), nullable=False, default="main")
    repo_full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    repo_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    workspace: Mapped["Workspace"] = relationship(back_populates="github_link")


class WatchFolder(Base):
    __tablename__ = "watch_folders"

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        primary_key=True,
    )
    path: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    last_scan_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    workspace: Mapped["Workspace"] = relationship(back_populates="watch_folder")


class File(Base):
    __tablename__ = "files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    storage_backend: Mapped[str] = mapped_column(
        String(16), nullable=False, default="local"
    )  # local | gcs
    gcs_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_gcs_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )  # pending | indexing | ocr | ready | failed | empty | needs_ocr
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    workspace: Mapped["Workspace"] = relationship(back_populates="files")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="New Chat")
    gcs_export_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    gcs_exported_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    workspace: Mapped["Workspace"] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sources_json: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # JSON string: [{filename, page, snippet}, ...]
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
    feedback: Mapped["MessageFeedback | None"] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
        uselist=False,
    )


class ChatMetric(Base):
    __tablename__ = "chat_metrics"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    route: Mapped[str] = mapped_column(String(32), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    file_source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    web_source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    had_trace: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class MessageFeedback(Base):
    __tablename__ = "message_feedback"

    message_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("messages.id", ondelete="CASCADE"),
        primary_key=True,
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    message: Mapped["Message"] = relationship(back_populates="feedback")


class Memory(Base):
    __tablename__ = "memory"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="memory")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    confidence: Mapped[float] = mapped_column(nullable=False, default=1.0)
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    workspace: Mapped["Workspace"] = relationship(back_populates="memories")


class PromptLog(Base):
    __tablename__ = "prompt_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    conversation_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    message_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="user")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_redacted: Mapped[str | None] = mapped_column(Text, nullable=True)
    chat_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="langgraph")
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class PromptPeriodStats(Base):
    __tablename__ = "prompt_period_stats"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    period_type: Mapped[str] = mapped_column(String(16), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    prompt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    distillation_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )
    distilled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class StudyConcept(Base):
    """Review concept card (Study workspace S1)."""

    __tablename__ = "study_concepts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    key_points_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    example: Mapped[str | None] = mapped_column(Text, nullable=True)
    sources_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    mastery: Mapped[str] = mapped_column(
        String(32), nullable=False, default="learning"
    )  # learning | reviewing | mastered
    source_file_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    workspace: Mapped["Workspace"] = relationship(back_populates="study_concepts")


class StudyQuestionSet(Base):
    """Practice question batch or practice test (Study workspace S1)."""

    __tablename__ = "study_question_sets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # practice | test
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    settings_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    workspace: Mapped["Workspace"] = relationship(back_populates="study_question_sets")
    questions: Mapped[list["StudyQuestion"]] = relationship(
        back_populates="question_set",
        cascade="all, delete-orphan",
        order_by="StudyQuestion.sort_order",
    )
    attempts: Mapped[list["StudyTestAttempt"]] = relationship(
        back_populates="question_set",
        cascade="all, delete-orphan",
    )


class StudyQuestion(Base):
    __tablename__ = "study_questions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    set_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("study_question_sets.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    question_type: Mapped[str] = mapped_column(String(32), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    options_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    correct_answer: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    solution_steps_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    sources_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    topic: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    question_set: Mapped["StudyQuestionSet"] = relationship(back_populates="questions")


class StudyTestAttempt(Base):
    __tablename__ = "study_test_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    set_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("study_question_sets.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    answers_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    score_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    started_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    question_set: Mapped["StudyQuestionSet"] = relationship(back_populates="attempts")
