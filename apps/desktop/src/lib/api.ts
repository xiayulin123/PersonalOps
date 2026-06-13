import type { WorkspaceType } from "@/lib/workspace-types";
import { getAuthToken } from "@/lib/auth";

/** Empty VITE_API_BASE = same origin (nginx proxies API in cloud Docker). */
function resolveApiBase(): string {
  const raw = import.meta.env.VITE_API_BASE;
  if (raw === undefined || raw === null) {
    return "http://localhost:8000";
  }
  return raw.trim();
}

const API_BASE = resolveApiBase();

export function getApiBase(): string {
  return API_BASE;
}

export async function apiFetch(
  path: string,
  init: RequestInit = {}
): Promise<Response> {
  const headers = new Headers(init.headers);
  const token = getAuthToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const url = path.startsWith("http") ? path : `${API_BASE}${path}`;
  return fetch(url, { ...init, headers });
}

export type AuthUser = {
  id: string;
  email: string;
  created_at: string;
};

export type AuthTokenResponse = {
  access_token: string;
  token_type: string;
  user: AuthUser;
};

export async function registerAuth(
  email: string,
  password: string
): Promise<AuthTokenResponse> {
  let res: Response;
  try {
    res = await apiFetch("/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
  } catch {
    throw new Error(
      "Cannot reach API. Start the backend on port 8000 (uvicorn main:app --reload --port 8000)."
    );
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail ?? "Registration failed");
  }
  return res.json();
}

export type AuthMessageResponse = {
  message: string;
};

async function postAuthMessage(
  path: string,
  body: Record<string, string>,
  fallbackError: string
): Promise<AuthMessageResponse> {
  let res: Response;
  try {
    res = await apiFetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new Error(
      "Cannot reach API. Start the backend on port 8000 (uvicorn main:app --reload --port 8000)."
    );
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail ?? fallbackError);
  }
  return res.json();
}

export async function registerStartAuth(
  email: string,
  password: string
): Promise<AuthMessageResponse> {
  return postAuthMessage(
    "/auth/register/start",
    { email, password },
    "Could not start registration"
  );
}

export async function registerVerifyAuth(
  email: string,
  code: string
): Promise<AuthTokenResponse> {
  let res: Response;
  try {
    res = await apiFetch("/auth/register/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, code }),
    });
  } catch {
    throw new Error(
      "Cannot reach API. Start the backend on port 8000 (uvicorn main:app --reload --port 8000)."
    );
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail ?? "Verification failed");
  }
  return res.json();
}

export async function registerResendAuth(email: string): Promise<AuthMessageResponse> {
  return postAuthMessage(
    "/auth/register/resend",
    { email },
    "Could not resend verification code"
  );
}

export async function forgotPasswordAuth(email: string): Promise<AuthMessageResponse> {
  return postAuthMessage(
    "/auth/forgot-password",
    { email },
    "Could not send reset code"
  );
}

export async function resetPasswordAuth(
  email: string,
  code: string,
  newPassword: string
): Promise<AuthMessageResponse> {
  return postAuthMessage(
    "/auth/reset-password",
    { email, code, new_password: newPassword },
    "Could not reset password"
  );
}

export async function loginAuth(
  email: string,
  password: string
): Promise<AuthTokenResponse> {
  let res: Response;
  try {
    res = await apiFetch("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
  } catch {
    throw new Error(
      "Cannot reach API. Start the backend on port 8000 (uvicorn main:app --reload --port 8000)."
    );
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail ?? "Login failed");
  }
  return res.json();
}

export async function fetchAuthMe(): Promise<AuthUser> {
  const res = await apiFetch("/auth/me");
  if (!res.ok) throw new Error("Not authenticated");
  return res.json();
}

export async function logoutAuth(): Promise<void> {
  await apiFetch("/auth/logout", { method: "POST" });
}

export type StorageStatus = {
  gcs_enabled: boolean;
  connection_ok: boolean;
  bucket: string | null;
  detail: string;
  user_prefix: string | null;
  credentials_path: string | null;
  total_bytes: number;
  conversation_exports_count: number;
  last_checked_at: string;
};

export async function fetchStorageStatus(): Promise<StorageStatus> {
  const res = await apiFetch("/me/storage/status");
  if (!res.ok) throw new Error("Failed to load storage status");
  return res.json();
}

export type CredentialProvider = "openai" | "tavily";

export type UserCredential = {
  provider: CredentialProvider;
  masked: string;
  configured: boolean;
  updated_at: string | null;
};

export type UserCredentialsResponse = {
  items: UserCredential[];
};

export async function fetchUserCredentials(): Promise<UserCredentialsResponse> {
  const res = await apiFetch("/me/credentials");
  if (!res.ok) throw new Error("Failed to load API keys");
  return res.json();
}

export async function upsertUserCredential(
  provider: CredentialProvider,
  secret: string
): Promise<UserCredential> {
  const res = await apiFetch("/me/credentials", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider, secret }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail ?? "Failed to save API key");
  }
  return res.json();
}

export type HealthStatus = {
    status: string;
    openai_configured: boolean;
    chroma_ok: boolean;
    web_provider: string;
    ocr_available: boolean;
    ocr_provider: string;
    github_configured: boolean;
    ripgrep_available: boolean;
    metrics_enabled: boolean;
    cursor_configured?: boolean;
    chat_default_mode?: string;
    outlook_configured?: boolean;
    google_configured?: boolean;
    deployment_mode?: string;
    cursor_agent_available?: boolean;
};

export type ChatMode = "langgraph" | "cursor_agent";

export async function checkHealth(): Promise<HealthStatus> {
    const res = await apiFetch(`/health`);
    if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
    return res.json();
}

export type Workspace = {
    id: string;
    name: string;
    type: WorkspaceType;
    chat_mode: ChatMode;
    created_at: string;
};

export type FileRecord = {
    id: string;
    workspace_id: string;
    filename: string;
    path: string;
    storage_backend?: "local" | "gcs" | string;
    gcs_uri?: string | null;
    size_bytes?: number;
    status:
        | "pending"
        | "indexing"
        | "ocr"
        | "ready"
        | "failed"
        | "empty"
        | "needs_ocr"
        | string;
    chunk_count: number;
};

export async function listWorkspaces(): Promise<Workspace[]> {
    const res = await apiFetch(`/workspaces`);
    if (!res.ok) throw new Error("Failed to list workspaces");
    return res.json();
}

export async function createWorkspace(
    name: string,
    type: WorkspaceType
): Promise<Workspace> {
    const res = await apiFetch(`/workspaces`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, type }),
    });
    if (!res.ok) throw new Error("Failed to create workspace");
    return res.json();
}

export async function deleteWorkspace(id: string): Promise<void> {
    const res = await apiFetch(`/workspaces/${id}`, { method: "DELETE" });
    if (!res.ok) throw new Error("Failed to delete workspace");
}

export async function getWorkspace(workspaceId: string): Promise<Workspace> {
    const res = await apiFetch(`/workspaces/${workspaceId}`);
    if (!res.ok) throw new Error("Failed to load workspace");
    return res.json();
}

export async function updateWorkspace(
    workspaceId: string,
    patch: { name?: string; chat_mode?: ChatMode }
): Promise<Workspace> {
    const res = await apiFetch(`/workspaces/${workspaceId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
    });
    if (!res.ok) throw new Error("Failed to update workspace");
    return res.json();
}

export type IndexingSummary = {
    ready: number;
    failed: number;
    needs_ocr: number;
    pending: number;
    indexing: number;
    ocr: number;
    empty: number;
    total: number;
};

export type OverviewFileItem = {
    filename: string;
    status: string;
    chunk_count: number;
    uploaded_at: string | null;
};

export type OverviewMessageItem = {
    role: string;
    content_preview: string;
    created_at: string | null;
};

export type SuggestedTemplate = {
    id: string;
    label: string;
    description: string;
};

export type WorkspaceOverview = {
    recent_files: OverviewFileItem[];
    recent_messages: OverviewMessageItem[];
    memory_count: number;
    tool_settings: Pick<ToolSettings, "file_search" | "web_search" | "memory">;
    indexing_summary: IndexingSummary;
    suggested_templates: SuggestedTemplate[];
};

export async function fetchWorkspaceOverview(
    workspaceId: string
): Promise<WorkspaceOverview> {
    const res = await apiFetch(`/workspaces/${workspaceId}/overview`);
    if (!res.ok) throw new Error("Failed to load workspace overview");
    return res.json();
}

export async function listFiles(workspaceId: string): Promise<FileRecord[]> {
    const res = await apiFetch(`/workspaces/${workspaceId}/files`);
    if (!res.ok) throw new Error("Failed to list files");
    return res.json();
}

export type WatchFolder = {
    workspace_id: string;
    path: string;
    enabled: boolean;
    last_scan_at: string | null;
};

export async function getWatchFolder(
    workspaceId: string
): Promise<WatchFolder | null> {
    const res = await apiFetch(`/workspaces/${workspaceId}/watcher`);
    if (!res.ok) throw new Error("Failed to load watch folder");
    const text = await res.text();
    if (!text) return null;
    return JSON.parse(text) as WatchFolder;
}

export async function saveWatchFolder(
    workspaceId: string,
    path: string,
    enabled = true
): Promise<WatchFolder> {
    const res = await apiFetch(`/workspaces/${workspaceId}/watcher`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path, enabled }),
    });
    if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        const detail =
            typeof body.detail === "string"
                ? body.detail
                : "Failed to save watch folder";
        throw new Error(detail);
    }
    return res.json();
}

export async function deleteWatchFolder(workspaceId: string): Promise<void> {
    const res = await apiFetch(`/workspaces/${workspaceId}/watcher`, {
        method: "DELETE",
    });
    if (!res.ok) throw new Error("Failed to stop folder watch");
}

export async function uploadFile(workspaceId: string, file: File): Promise<FileRecord> {
    const form = new FormData();
    form.append("file", file);
    const res = await apiFetch(`/workspaces/${workspaceId}/files`, {
        method: "POST",
        body: form,
    });
    if (!res.ok) throw new Error("Upload failed");
    return res.json();
}

export async function deleteFile(workspaceId: string, fileId: string): Promise<void> {
    const res = await apiFetch(`/workspaces/${workspaceId}/files/${fileId}`, {
        method: "DELETE",
    });
    if (!res.ok) throw new Error("Failed to delete file");
}

export async function runFileOcr(workspaceId: string, fileId: string): Promise<FileRecord> {
    const res = await apiFetch(`/workspaces/${workspaceId}/files/${fileId}/ocr`, {
        method: "POST",
    });
    if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        const detail =
            typeof body.detail === "string"
                ? body.detail
                : "Failed to start OCR";
        throw new Error(detail);
    }
    return res.json();
}

export type MemoryRecord = {
    id: string;
    workspace_id: string;
    key: string;
    value: string;
    source?: string;
    kind?: string;
    status?: string;
    confidence?: number;
    period_start?: string | null;
};

export type PersonalizationSettings = {
    auto_learn_enabled: boolean;
    require_approval: boolean;
    auto_learn_override: boolean | null;
    require_approval_override: boolean | null;
    global_auto_learn_enabled: boolean;
    global_require_approval: boolean;
    cloud_archive_enabled: boolean;
    cloud_archive_provider: string;
    cloud_archive_configured: boolean;
};

export type PersonalizationStats = {
    enabled: boolean;
    today_count: number;
    week_count: number;
    daily_threshold: number;
    weekly_threshold: number;
    today_distillation_status: string;
    week_distillation_status: string;
    period_day: string;
    period_week_start: string;
};

export async function listMemory(workspaceId: string): Promise<MemoryRecord[]> {
    const res = await apiFetch(`/workspaces/${workspaceId}/memory`);
    if (!res.ok) throw new Error("Failed to list memory");
    return res.json();
}

export async function createMemory(
    workspaceId: string,
    key: string,
    value: string
): Promise<MemoryRecord> {
    const res = await apiFetch(`/workspaces/${workspaceId}/memory`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key, value }),
    });
    if (!res.ok) throw new Error("Failed to create memory");
    return res.json();
}

export async function updateMemory(
    workspaceId: string,
    memoryId: string,
    value: string
): Promise<MemoryRecord> {
    const res = await apiFetch(`/workspaces/${workspaceId}/memory/${memoryId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ value }),
    });
    if (!res.ok) throw new Error("Failed to update memory");
    return res.json();
}

export async function deleteMemory(workspaceId: string, memoryId: string): Promise<void> {
    const res = await apiFetch(`/workspaces/${workspaceId}/memory/${memoryId}`, {
        method: "DELETE",
    });
    if (!res.ok) throw new Error("Failed to delete memory");
}

export async function listPersonalizationDrafts(
    workspaceId: string
): Promise<MemoryRecord[]> {
    const res = await apiFetch(`/workspaces/${workspaceId}/personalization/drafts`);
    if (!res.ok) throw new Error("Failed to list learned drafts");
    return res.json();
}

export async function adoptPersonalizationDraft(
    workspaceId: string,
    memoryId: string
): Promise<MemoryRecord> {
    const res = await apiFetch(
        `/workspaces/${workspaceId}/personalization/drafts/${memoryId}/adopt`,
        { method: "POST" }
    );
    if (!res.ok) throw new Error("Failed to adopt draft");
    return res.json();
}

export async function rejectPersonalizationDraft(
    workspaceId: string,
    memoryId: string
): Promise<MemoryRecord> {
    const res = await apiFetch(
        `/workspaces/${workspaceId}/personalization/drafts/${memoryId}/reject`,
        { method: "POST" }
    );
    if (!res.ok) throw new Error("Failed to reject draft");
    return res.json();
}

export async function adoptAllPersonalizationDrafts(
    workspaceId: string
): Promise<{ adopted: number }> {
    const res = await apiFetch(
        `/workspaces/${workspaceId}/personalization/drafts/adopt-all`,
        { method: "POST" }
    );
    if (!res.ok) throw new Error("Failed to adopt all drafts");
    return res.json();
}

export async function getPersonalizationSettings(
    workspaceId: string
): Promise<PersonalizationSettings> {
    const res = await apiFetch(`/workspaces/${workspaceId}/personalization/settings`);
    if (!res.ok) throw new Error("Failed to load personalization settings");
    return res.json();
}

export async function updatePersonalizationSettings(
    workspaceId: string,
    patch: Partial<Pick<PersonalizationSettings, "auto_learn_enabled" | "require_approval">>
): Promise<PersonalizationSettings> {
    const res = await apiFetch(`/workspaces/${workspaceId}/personalization/settings`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
    });
    if (!res.ok) throw new Error("Failed to update personalization settings");
    return res.json();
}

export async function wipePersonalizationData(
    workspaceId: string
): Promise<{
    prompt_logs_deleted: number;
    period_stats_deleted: number;
    auto_memory_deleted: number;
}> {
    const res = await apiFetch(`/workspaces/${workspaceId}/personalization/data`, {
        method: "DELETE",
    });
    if (!res.ok) throw new Error("Failed to wipe personalization data");
    return res.json();
}

export async function getPersonalizationStats(
    workspaceId: string
): Promise<PersonalizationStats> {
    const res = await apiFetch(`/workspaces/${workspaceId}/personalization/stats`);
    if (!res.ok) throw new Error("Failed to load personalization stats");
    return res.json();
}

export type PersonalizationDistillResult = {
    workspace_id?: string;
    period_type?: string;
    period_start?: string;
    status: string;
    written?: number;
    skipped?: boolean;
    reason?: string;
    error?: string;
};

export async function distillPersonalization(
    workspaceId: string,
    period: "day" | "week" = "day",
    force = false
): Promise<PersonalizationDistillResult> {
    const params = new URLSearchParams({ period, force: String(force) });
    const res = await apiFetch(
        `/workspaces/${workspaceId}/personalization/distill?${params}`,
        { method: "POST" }
    );
    if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        const detail = typeof body.detail === "string" ? body.detail : "Distill failed";
        throw new Error(detail);
    }
    return res.json();
}

export type ToolSettings = {
    file_search: boolean;
    web_search: boolean;
    memory: boolean;
    github_read: boolean;
    code_search: boolean;
    available: string[];
};

export type GitHubLink = {
    workspace_id: string;
    repo_url: string;
    default_branch: string;
    repo_full_name: string | null;
    repo_description: string | null;
    last_synced_at: string | null;
};

export type GitHubSyncResult = {
    repo_full_name: string | null;
    default_branch: string;
    last_synced_at: string | null;
    synced_files: { filename: string; status: string; chunk_count: number }[];
    readme_synced: boolean;
    issues_synced: boolean;
};

export async function getGitHubLink(
    workspaceId: string
): Promise<GitHubLink | null> {
    const res = await apiFetch(`/workspaces/${workspaceId}/github`);
    if (!res.ok) throw new Error("Failed to load GitHub link");
    const text = await res.text();
    if (!text) return null;
    return JSON.parse(text) as GitHubLink;
}

export async function saveGitHubLink(
    workspaceId: string,
    repoUrl: string
): Promise<GitHubLink> {
    const res = await apiFetch(`/workspaces/${workspaceId}/github`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo_url: repoUrl }),
    });
    if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        const detail =
            typeof body.detail === "string" ? body.detail : "Failed to save GitHub link";
        throw new Error(detail);
    }
    return res.json();
}

export async function syncGitHubRepo(
    workspaceId: string
): Promise<GitHubSyncResult> {
    const res = await apiFetch(`/workspaces/${workspaceId}/github/sync`, {
        method: "POST",
    });
    if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        const detail =
            typeof body.detail === "string" ? body.detail : "Failed to sync GitHub repo";
        throw new Error(detail);
    }
    return res.json();
}

export async function getToolSettings(workspaceId: string): Promise<ToolSettings> {
    const res = await apiFetch(`/workspaces/${workspaceId}/tools`);
    if (!res.ok) throw new Error("Failed to load tool settings");
    return res.json();
}

export async function updateToolSettings(
    workspaceId: string,
    patch: Partial<
        Pick<
            ToolSettings,
            "file_search" | "web_search" | "memory" | "github_read" | "code_search"
        >
    >
): Promise<ToolSettings> {
    const res = await apiFetch(`/workspaces/${workspaceId}/tools`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
    });
    if (!res.ok) throw new Error("Failed to update tool settings");
    return res.json();
}

export type ChatSource = {
    filename: string;
    page: number;
    line?: number;
    snippet: string;
    source_type?: string;
};

export type WebSource = {
    title: string;
    url: string;
    snippet: string;
};

export type AgentStep = {
    step: number;
    label: string;
    detail?: string;
};

export type ChatResponse = {
    answer: string;
    sources: ChatSource[];
    web_sources?: WebSource[];
    trace?: AgentStep[];
    route?: string;
    chat_engine?: ChatMode | string | null;
    agent_label?: string | null;
    assistant_message_id?: string | null;
};

export type ChatMessageRecord = {
    id: string;
    role: "user" | "assistant";
    content: string;
    sources?: ChatSource[];
    web_sources?: WebSource[];
    trace?: AgentStep[];
    route?: string;
    chat_engine?: ChatMode | string | null;
    agent_label?: string | null;
    feedback_rating?: number | null;
};

export type ConversationRecord = {
    id: string;
    title: string;
    message_count: number;
};

export async function listConversations(
    workspaceId: string
): Promise<ConversationRecord[]> {
    const res = await apiFetch(`/workspaces/${workspaceId}/chat/conversations`);
    if (!res.ok) throw new Error("Failed to load conversations");
    return res.json();
}

export async function createConversation(
    workspaceId: string
): Promise<ConversationRecord> {
    const res = await apiFetch(`/workspaces/${workspaceId}/chat/conversations`, {
        method: "POST",
    });
    if (!res.ok) throw new Error("Failed to create conversation");
    return res.json();
}

export async function listChatMessages(
    workspaceId: string,
    conversationId?: string | null
): Promise<ChatMessageRecord[]> {
    const query = conversationId
        ? `?conversation_id=${encodeURIComponent(conversationId)}`
        : "";
    const res = await apiFetch(
        `/workspaces/${workspaceId}/chat/messages${query}`
    );
    if (!res.ok) throw new Error("Failed to load chat messages");
    return res.json();
}

export type MetricsSummary = {
    total_chats: number;
    avg_latency_ms: number;
    citation_rate: number;
    route_breakdown: Record<string, number>;
    feedback_up: number;
    feedback_down: number;
};

export async function getMetricsSummary(
    workspaceId: string
): Promise<MetricsSummary> {
    const res = await apiFetch(`/workspaces/${workspaceId}/metrics/summary`);
    if (!res.ok) throw new Error("Failed to load metrics summary");
    return res.json();
}

export async function submitMessageFeedback(
    messageId: string,
    rating: 1 | 5
): Promise<void> {
    const res = await apiFetch(`/messages/${messageId}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rating }),
    });
    if (!res.ok) throw new Error("Failed to submit feedback");
}

export type TaskTemplate = {
    id: string;
    label: string;
    description: string;
};

export async function listTemplates(workspaceId: string): Promise<TaskTemplate[]> {
    const res = await apiFetch(`/workspaces/${workspaceId}/templates`);
    if (!res.ok) throw new Error("Failed to list templates");
    return res.json();
}

export async function sendChat(
    workspaceId: string,
    message: string,
    templateId?: string | null,
    conversationId?: string | null
): Promise<ChatResponse> {
    const payload: {
        message: string;
        template_id?: string;
        conversation_id?: string;
    } = { message };
    if (templateId) {
        payload.template_id = templateId;
    }
    if (conversationId) {
        payload.conversation_id = conversationId;
    }
    const res = await apiFetch(`/workspaces/${workspaceId}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error("Chat failed");
    return res.json();
}

function parseSseChunk(
    buffer: string,
    onEvent: (event: string, data: string) => void
): string {
    const parts = buffer.split("\n\n");
    const remainder = parts.pop() ?? "";

    for (const part of parts) {
        if (!part.trim()) continue;

        let event = "message";
        const dataLines: string[] = [];

        for (const line of part.split("\n")) {
            if (line.startsWith("event:")) {
                event = line.slice(6).trim();
            } else if (line.startsWith("data:")) {
                dataLines.push(line.slice(5).trim());
            }
        }

        if (dataLines.length > 0) {
            onEvent(event, dataLines.join("\n"));
        }
    }

    return remainder;
}

export class ChatStreamAbortedError extends Error {
    readonly aborted = true;

    constructor() {
        super("Chat stream aborted");
        this.name = "ChatStreamAbortedError";
    }
}

function isStreamAbortError(err: unknown): boolean {
    return (
        err instanceof ChatStreamAbortedError ||
        (err instanceof DOMException && err.name === "AbortError") ||
        (err instanceof Error && err.name === "AbortError")
    );
}

export async function sendChatStream(
    workspaceId: string,
    message: string,
    onStep: (step: AgentStep) => void,
    templateId?: string | null,
    signal?: AbortSignal,
    conversationId?: string | null
): Promise<ChatResponse> {
    const payload: {
        message: string;
        template_id?: string;
        conversation_id?: string;
    } = { message };
    if (templateId) {
        payload.template_id = templateId;
    }
    if (conversationId) {
        payload.conversation_id = conversationId;
    }

    const res = await apiFetch(`/workspaces/${workspaceId}/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal,
    });

    if (!res.ok) {
        throw new Error("Chat stream failed");
    }

    const reader = res.body?.getReader();
    if (!reader) {
        throw new Error("Chat stream body missing");
    }

    const decoder = new TextDecoder();
    let buffer = "";
    let finalResponse: ChatResponse | null = null;

    try {
        while (true) {
            if (signal?.aborted) {
                throw new ChatStreamAbortedError();
            }

            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            buffer = parseSseChunk(buffer, (event, data) => {
                if (event === "step") {
                    const step = JSON.parse(data) as AgentStep;
                    onStep(step);
                    return;
                }

                if (event === "done") {
                    finalResponse = JSON.parse(data) as ChatResponse;
                    return;
                }

                if (event === "error") {
                    const errorPayload = JSON.parse(data) as { detail?: string };
                    throw new Error(errorPayload.detail ?? "Chat stream error");
                }
            });
        }

        if (signal?.aborted) {
            throw new ChatStreamAbortedError();
        }

        if (buffer.trim()) {
            parseSseChunk(`${buffer}\n\n`, (event, data) => {
                if (event === "step") {
                    onStep(JSON.parse(data) as AgentStep);
                } else if (event === "done") {
                    finalResponse = JSON.parse(data) as ChatResponse;
                } else if (event === "error") {
                    const errorPayload = JSON.parse(data) as { detail?: string };
                    throw new Error(errorPayload.detail ?? "Chat stream error");
                }
            });
        }

        if (!finalResponse) {
            throw new Error("Chat stream ended without a final response");
        }

        return finalResponse;
    } catch (err) {
        if (isStreamAbortError(err)) {
            throw new ChatStreamAbortedError();
        }
        throw err;
    } finally {
        try {
            await reader.cancel();
        } catch {
            // Reader may already be closed after abort or completion.
        }
    }
}

export type LifeOutlookStatus = {
    configured: boolean;
    connected: boolean;
    account_email?: string | null;
    last_mail_sync_at?: string | null;
    last_calendar_sync_at?: string | null;
};

export type LifeConnectionProvider = {
    id: string;
    label: string;
    configured: boolean;
    connected: boolean;
    account_email?: string | null;
    features: string[];
    last_mail_sync_at?: string | null;
    last_calendar_sync_at?: string | null;
};

export type LifeConnections = {
    providers: LifeConnectionProvider[];
};

export type InboxBrief = {
    id: string;
    subject: string;
    from_address: string;
    from_name?: string | null;
    received_at: string;
    body_preview: string;
    summary: string;
    summary_engine: string;
    provider?: string;
};

export type LifeCalendarEvent = {
    id: string;
    subject: string;
    start_at: string;
    end_at: string;
    location?: string | null;
    is_all_day: boolean;
    organizer?: string | null;
    provider?: string;
};

export async function getLifeOutlookStatus(
    workspaceId: string
): Promise<LifeOutlookStatus> {
    const res = await apiFetch(`/workspaces/${workspaceId}/life/outlook/status`);
    if (!res.ok) throw new Error("Failed to load Outlook status");
    return res.json();
}

export async function getLifeConnections(workspaceId: string): Promise<LifeConnections> {
    const res = await apiFetch(`/workspaces/${workspaceId}/life/connections`);
    if (!res.ok) throw new Error("Failed to load connections");
    return res.json();
}

export async function startOutlookOAuth(workspaceId: string): Promise<{
    authorize_url: string;
    state: string;
    expires_in_sec: number;
}> {
    const res = await apiFetch(
        `/workspaces/${workspaceId}/life/outlook/oauth/start`
    );
    if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? "Failed to start Microsoft sign-in");
    }
    return res.json();
}

export async function startGoogleOAuth(workspaceId: string): Promise<{
    authorize_url: string;
    state: string;
    expires_in_sec: number;
}> {
    const res = await apiFetch(
        `/workspaces/${workspaceId}/life/google/oauth/start`
    );
    if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? "Failed to start Google sign-in");
    }
    return res.json();
}

export async function completeGoogleOAuth(
    workspaceId: string,
    body: { code: string; state: string }
): Promise<LifeOutlookStatus> {
    const res = await apiFetch(
        `/workspaces/${workspaceId}/life/google/oauth/callback`,
        {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        }
    );
    if (!res.ok) {
        const payload = await res.json().catch(() => ({}));
        throw new Error(payload.detail ?? "Google sign-in failed");
    }
    return res.json();
}

export async function disconnectGoogle(workspaceId: string): Promise<void> {
    const res = await apiFetch(`/workspaces/${workspaceId}/life/google`, {
        method: "DELETE",
    });
    if (!res.ok) throw new Error("Failed to disconnect Google");
}

export async function completeOutlookOAuth(
    workspaceId: string,
    body: { code: string; state: string }
): Promise<LifeOutlookStatus> {
    const res = await apiFetch(
        `/workspaces/${workspaceId}/life/outlook/oauth/callback`,
        {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        }
    );
    if (!res.ok) {
        const payload = await res.json().catch(() => ({}));
        throw new Error(payload.detail ?? "Microsoft sign-in failed");
    }
    return res.json();
}

export async function startOutlookDeviceCode(workspaceId: string): Promise<{
    user_code: string;
    verification_uri: string;
    message: string;
    device_code: string;
}> {
    const res = await apiFetch(
        `/workspaces/${workspaceId}/life/outlook/device-code/start`,
        { method: "POST" }
    );
    if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? "Failed to start Outlook sign-in");
    }
    return res.json();
}

export async function pollOutlookDeviceCode(
    workspaceId: string,
    deviceCode: string
): Promise<LifeOutlookStatus> {
    const res = await apiFetch(
        `/workspaces/${workspaceId}/life/outlook/device-code/poll`,
        {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ device_code: deviceCode }),
        }
    );
    if (res.status === 202) {
        throw new Error("pending");
    }
    if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? "Outlook sign-in failed");
    }
    return res.json();
}

export async function disconnectOutlook(workspaceId: string): Promise<void> {
    const res = await apiFetch(`/workspaces/${workspaceId}/life/outlook`, {
        method: "DELETE",
    });
    if (!res.ok) throw new Error("Failed to disconnect Outlook");
}

export async function listLifeInbox(
    workspaceId: string,
    pageSize = 5,
    page = 0
): Promise<{
    connected: boolean;
    items: InboxBrief[];
    unread: InboxBrief[];
    viewed: InboxBrief[];
    historical: InboxBrief[];
    total_unread: number;
    page: number;
    page_size: number;
    total_pages: number;
}> {
    const params = new URLSearchParams({
        page_size: String(pageSize),
        page: String(page),
    });
    const res = await apiFetch(
        `/workspaces/${workspaceId}/life/inbox?${params}`
    );
    if (!res.ok) throw new Error("Failed to load inbox");
    return res.json();
}

export async function dismissAllInboxBriefs(workspaceId: string): Promise<void> {
    const res = await apiFetch(
        `/workspaces/${workspaceId}/life/inbox/dismiss-all`,
        { method: "POST" }
    );
    if (!res.ok) throw new Error("Failed to mark all as read");
}

export async function dismissInboxBrief(
    workspaceId: string,
    briefId: string
): Promise<void> {
    const res = await apiFetch(
        `/workspaces/${workspaceId}/life/inbox/${briefId}/dismiss`,
        { method: "POST" }
    );
    if (!res.ok) throw new Error("Failed to dismiss brief");
}

export async function listLifeCalendar(
    workspaceId: string,
    days = 7
): Promise<{ connected: boolean; events: LifeCalendarEvent[] }> {
    const res = await apiFetch(
        `/workspaces/${workspaceId}/life/calendar?days=${days}`
    );
    if (!res.ok) throw new Error("Failed to load calendar");
    return res.json();
}

export async function syncLifePlugins(workspaceId: string): Promise<{
    new_mail_briefs: number;
    calendar_events: number;
}> {
    const res = await apiFetch(`/workspaces/${workspaceId}/life/sync`, {
        method: "POST",
    });
    if (!res.ok) throw new Error("Failed to sync life plugins");
    return res.json();
}