from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

WorkspaceType = Literal["study", "code", "life", "career"]
WORKSPACE_TYPES = frozenset({"study", "code", "life", "career"})


class WorkspaceCreate(BaseModel):
    name: str
    type: WorkspaceType


class AuthRegisterIn(BaseModel):
    email: str
    password: str


class AuthLoginIn(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AuthTokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


ChatMode = Literal["langgraph", "cursor_agent"]


class WorkspaceOut(BaseModel):
    id: str
    name: str
    type: str
    chat_mode: str = "langgraph"
    created_at: datetime

    model_config = {"from_attributes": True}


class WorkspaceUpdate(BaseModel):
    name: str | None = None
    chat_mode: ChatMode | None = None


class FileOut(BaseModel):
    id: str
    workspace_id: str
    filename: str
    path: str
    storage_backend: str = "local"
    gcs_uri: str | None = None
    extracted_gcs_uri: str | None = None
    size_bytes: int = 0
    status: str
    chunk_count: int

    model_config = {"from_attributes": True}


class StorageStatusOut(BaseModel):
    gcs_enabled: bool
    connection_ok: bool
    bucket: str | None = None
    detail: str
    user_prefix: str | None = None
    credentials_path: str | None = None
    total_bytes: int = 0
    conversation_exports_count: int = 0
    last_checked_at: str


CredentialProvider = Literal["openai", "tavily", "cursor", "github"]


class UserCredentialOut(BaseModel):
    provider: CredentialProvider
    masked: str
    configured: bool
    updated_at: str | None = None


class UserCredentialsOut(BaseModel):
    items: list[UserCredentialOut]


class UserCredentialUpsertIn(BaseModel):
    provider: CredentialProvider
    secret: str = ""


class MemoryCreate(BaseModel):
    key: str
    value: str


class MemoryUpdate(BaseModel):
    value: str


class MemoryOut(BaseModel):
    id: str
    workspace_id: str
    key: str
    value: str
    source: str = "manual"
    kind: str = "memory"
    status: str = "active"
    confidence: float = 1.0
    period_start: date | None = None

    model_config = {"from_attributes": True}


class ToolSettings(BaseModel):
    file_search: bool = True
    web_search: bool = False
    memory: bool = True
    github_read: bool = False
    code_search: bool = False


class ToolSettingsUpdate(BaseModel):
    file_search: bool | None = None
    web_search: bool | None = None
    memory: bool | None = None
    github_read: bool | None = None
    code_search: bool | None = None


class GitHubLinkUpdate(BaseModel):
    repo_url: str


class GitHubLinkOut(BaseModel):
    workspace_id: str
    repo_url: str
    default_branch: str
    repo_full_name: str | None = None
    repo_description: str | None = None
    last_synced_at: datetime | None = None

    model_config = {"from_attributes": True}


class GitHubSyncedFileOut(BaseModel):
    filename: str
    status: str
    chunk_count: int


class WatchFolderUpdate(BaseModel):
    path: str
    enabled: bool = True


class WatchFolderOut(BaseModel):
    workspace_id: str
    path: str
    enabled: bool
    last_scan_at: datetime | None = None

    model_config = {"from_attributes": True}


class GitHubSyncOut(BaseModel):
    repo_full_name: str | None = None
    default_branch: str
    last_synced_at: datetime | None = None
    synced_files: list[GitHubSyncedFileOut]
    readme_synced: bool
    issues_synced: bool


class ToolSettingsOut(ToolSettings):
    available: list[str]


class TemplateOut(BaseModel):
    id: str
    label: str
    description: str


class ChatRequest(BaseModel):
    message: str
    template_id: str | None = None
    conversation_id: str | None = None


class ConversationOut(BaseModel):
    id: str
    title: str
    message_count: int = 0
    last_used_at: datetime | None = None

    model_config = {"from_attributes": True}


class SourceOut(BaseModel):
    filename: str
    page: int
    snippet: str


class WebSourceOut(BaseModel):
    title: str
    url: str
    snippet: str


class AgentStepOut(BaseModel):
    step: int
    label: str
    detail: str | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceOut]
    web_sources: list[WebSourceOut] = []
    trace: list[AgentStepOut] = []
    route: str | None = None
    chat_engine: str | None = None
    agent_label: str | None = None
    assistant_message_id: str | None = None


class ChatMessageOut(BaseModel):
    id: str
    role: str
    content: str
    sources: list[SourceOut] = []
    web_sources: list[WebSourceOut] = []
    trace: list[AgentStepOut] = []
    route: str | None = None
    chat_engine: str | None = None
    agent_label: str | None = None
    feedback_rating: int | None = None


class MessageFeedbackUpdate(BaseModel):
    rating: int


class HealthOut(BaseModel):
    status: str
    openai_configured: bool
    chroma_ok: bool
    web_provider: str
    ocr_available: bool
    ocr_provider: str
    github_configured: bool
    ripgrep_available: bool
    metrics_enabled: bool
    cursor_configured: bool = False
    chat_default_mode: str = "langgraph"
    outlook_configured: bool = False
    google_configured: bool = False
    deployment_mode: str = "local"
    cursor_agent_available: bool = True


class DeviceCodeStartOut(BaseModel):
    user_code: str
    verification_uri: str
    message: str
    device_code: str


class DeviceCodePollIn(BaseModel):
    device_code: str


class LifeOutlookStatusOut(BaseModel):
    configured: bool
    connected: bool
    account_email: str | None = None
    last_mail_sync_at: datetime | None = None
    last_calendar_sync_at: datetime | None = None


class OAuthStartOut(BaseModel):
    authorize_url: str
    state: str
    expires_in_sec: int


class OAuthCallbackIn(BaseModel):
    code: str
    state: str


class LifeConnectionProviderOut(BaseModel):
    id: str
    label: str
    configured: bool
    connected: bool
    account_email: str | None = None
    features: list[str]
    last_mail_sync_at: datetime | None = None
    last_calendar_sync_at: datetime | None = None


class LifeConnectionsOut(BaseModel):
    providers: list[LifeConnectionProviderOut]


class InboxBriefOut(BaseModel):
    id: str
    subject: str
    from_address: str
    from_name: str | None = None
    received_at: datetime
    body_preview: str
    summary: str
    summary_engine: str
    provider: str = "microsoft"

    model_config = {"from_attributes": True}


class InboxListOut(BaseModel):
    connected: bool
    items: list[InboxBriefOut]
    unread: list[InboxBriefOut] = []
    viewed: list[InboxBriefOut] = []
    historical: list[InboxBriefOut] = []
    total_unread: int = 0
    page: int = 0
    page_size: int = 5
    total_pages: int = 0


class CalendarEventOut(BaseModel):
    id: str
    subject: str
    start_at: datetime
    end_at: datetime
    location: str | None = None
    is_all_day: bool
    organizer: str | None = None
    provider: str = "microsoft"

    model_config = {"from_attributes": True}


class LifeCalendarOut(BaseModel):
    connected: bool
    events: list[CalendarEventOut]


class LifeSyncOut(BaseModel):
    new_mail_briefs: int
    calendar_events: int


class MetricsSummaryOut(BaseModel):
    total_chats: int
    avg_latency_ms: int
    citation_rate: float
    route_breakdown: dict[str, int]
    feedback_up: int
    feedback_down: int


class OverviewFileItem(BaseModel):
    filename: str
    status: str
    chunk_count: int
    uploaded_at: datetime | None = None


class OverviewMessageItem(BaseModel):
    role: str
    content_preview: str
    created_at: datetime | None = None


class IndexingSummary(BaseModel):
    ready: int = 0
    failed: int = 0
    needs_ocr: int = 0
    pending: int = 0
    indexing: int = 0
    ocr: int = 0
    empty: int = 0
    total: int = 0


class SuggestedTemplateOut(BaseModel):
    id: str
    label: str
    description: str


class WorkspaceOverviewOut(BaseModel):
    recent_files: list[OverviewFileItem]
    recent_messages: list[OverviewMessageItem]
    memory_count: int
    tool_settings: ToolSettings
    indexing_summary: IndexingSummary
    suggested_templates: list[SuggestedTemplateOut]


class PersonalizationStatsOut(BaseModel):
    enabled: bool
    today_count: int
    week_count: int
    daily_threshold: int
    weekly_threshold: int
    today_distillation_status: str
    week_distillation_status: str
    period_day: str
    period_week_start: str


class PersonalizationDistillOut(BaseModel):
    workspace_id: str | None = None
    period_type: str | None = None
    period_start: str | None = None
    status: str
    written: int = 0
    skipped: bool = False
    reason: str | None = None
    error: str | None = None


class PersonalizationSettingsOut(BaseModel):
    auto_learn_enabled: bool
    require_approval: bool
    auto_learn_override: bool | None = None
    require_approval_override: bool | None = None
    global_auto_learn_enabled: bool
    global_require_approval: bool
    cloud_archive_enabled: bool = False
    cloud_archive_provider: str = "gcs"
    cloud_archive_configured: bool = False


class PersonalizationSettingsUpdate(BaseModel):
    auto_learn_enabled: bool | None = None
    require_approval: bool | None = None


class PersonalizationArchiveOut(BaseModel):
    workspace_id: str | None = None
    period_start: str | None = None
    status: str
    record_count: int = 0
    uri: str | None = None
    skipped: bool = False
    reason: str | None = None
    error: str | None = None


class PersonalizationWipeOut(BaseModel):
    prompt_logs_deleted: int
    period_stats_deleted: int
    auto_memory_deleted: int


class PersonalizationAdoptAllOut(BaseModel):
    adopted: int