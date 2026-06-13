import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  Bot,
  FileSearch,
  FolderGit,
  Globe,
  Loader2,
  SearchCode,
  SlidersHorizontal,
  Sparkles,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  checkHealth,
  getGitHubLink,
  getToolSettings,
  saveGitHubLink,
  syncGitHubRepo,
  updateToolSettings,
  updateWorkspace,
  type ChatMode,
  type GitHubLink,
  type ToolSettings,
  type Workspace,
} from "@/lib/api";
import {
  CURSOR_AGENT_DESKTOP_DESCRIPTION,
  CURSOR_AGENT_DESKTOP_TOOLTIP,
  isCloudEdition,
  isCursorAgentUiDisabled,
  UI_CHAT_ENGINE_MODES,
} from "@/lib/edition";
import { cn } from "@/lib/utils";

type ToolsTabProps = {
  workspace: Workspace;
  onWorkspaceUpdated?: (workspace: Workspace) => void;
};

const CHAT_ENGINE_META: Record<
  ChatMode,
  { label: string; description: string; icon: typeof Bot }
> = {
  langgraph: {
    label: "LangGraph RAG",
    description:
      "Classic pipeline: classify route, Chroma vector search, OpenAI generate + verify.",
    icon: Sparkles,
  },
  cursor_agent: {
    label: "Cursor Agent",
    description:
      "Cursor Agent reads files directly under uploads/ (no embedding). Memory syncs to .cursor/rules.",
    icon: Bot,
  },
};

type ToolKey = "file_search" | "web_search" | "memory" | "github_read" | "code_search";

const TOOL_META: Record<
  ToolKey,
  { label: string; description: string; icon: typeof FileSearch }
> = {
  file_search: {
    label: "File search",
    description:
      "Let the agent retrieve chunks from uploaded workspace files (RAG) when answering.",
    icon: FileSearch,
  },
  web_search: {
    label: "Web search",
    description:
      "Let the agent search the web for current information (Tavily or DuckDuckGo fallback).",
    icon: Globe,
  },
  memory: {
    label: "Memory",
    description:
      "Inject workspace memory into the agent. Cursor mode also writes .cursor/rules/personalops-memory.mdc.",
    icon: SlidersHorizontal,
  },
  github_read: {
    label: "GitHub read",
    description:
      "Let the agent use synced GitHub README and open issues indexed in this workspace.",
    icon: FolderGit,
  },
  code_search: {
    label: "Code search",
    description:
      "Run ripgrep keyword search on uploaded code files for exact line matches (functions, classes, errors).",
    icon: SearchCode,
  },
};

function ToolToggle({
  checked,
  disabled,
  onChange,
  label,
}: {
  checked: boolean;
  disabled?: boolean;
  onChange: (next: boolean) => void;
  label: string;
}) {
  return (
    <div className="flex items-center gap-2.5">
      <span
        className={cn(
          "min-w-[2rem] text-right text-xs font-semibold uppercase tracking-wide",
          checked ? "text-primary" : "text-muted-foreground"
        )}
      >
        {checked ? "On" : "Off"}
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cn(
          "relative inline-flex h-7 w-12 shrink-0 rounded-full border-2 transition-colors",
          "focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/40",
          checked
            ? "border-primary bg-primary"
            : "border-foreground/30 bg-foreground/10",
          disabled && "cursor-not-allowed opacity-50"
        )}
      >
        <span
          className={cn(
            "pointer-events-none absolute top-0.5 size-5 rounded-full border shadow-md transition-transform",
            checked
              ? "translate-x-[1.35rem] border-primary/20 bg-primary-foreground"
              : "translate-x-0.5 border-foreground/20 bg-background"
          )}
        />
      </button>
    </div>
  );
}

function formatSyncedAt(value: string | null) {
  if (!value) return "Never synced";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

export function ToolsTab({ workspace, onWorkspaceUpdated }: ToolsTabProps) {
  const workspaceId = workspace.id;
  const workspaceType = workspace.type;
  const [chatMode, setChatMode] = useState<ChatMode>(
    workspace.chat_mode ?? "langgraph"
  );
  const [savingChatMode, setSavingChatMode] = useState(false);
  const [cursorConfigured, setCursorConfigured] = useState<boolean | null>(null);
  const [settings, setSettings] = useState<ToolSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [savingKey, setSavingKey] = useState<ToolKey | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [githubLink, setGithubLink] = useState<GitHubLink | null>(null);
  const [repoUrl, setRepoUrl] = useState("");
  const [githubLoading, setGithubLoading] = useState(false);
  const [githubSaving, setGithubSaving] = useState(false);
  const [githubSyncing, setGithubSyncing] = useState(false);
  const [githubMessage, setGithubMessage] = useState<string | null>(null);

  const loadSettings = useCallback(async () => {
    try {
      const data = await getToolSettings(workspaceId);
      setSettings(data);
      setError(null);
    } catch {
      setError("Failed to load tool settings");
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  const loadGitHub = useCallback(async () => {
    if (workspaceType !== "code") return;
    setGithubLoading(true);
    try {
      const link = await getGitHubLink(workspaceId);
      setGithubLink(link);
      setRepoUrl(link?.repo_url ?? "");
      setGithubMessage(null);
    } catch {
      setGithubMessage("Failed to load GitHub link");
    } finally {
      setGithubLoading(false);
    }
  }, [workspaceId, workspaceType]);

  useEffect(() => {
    setChatMode(workspace.chat_mode ?? "langgraph");
  }, [workspace.chat_mode, workspace.id]);

  useEffect(() => {
    setLoading(true);
    loadSettings();
    void loadGitHub();
    void checkHealth()
      .then((health) => setCursorConfigured(Boolean(health.cursor_configured)))
      .catch(() => setCursorConfigured(false));
  }, [loadSettings, loadGitHub]);

  async function handleChatModeChange(next: ChatMode) {
    if (next === chatMode || savingChatMode) return;
    if (next === "cursor_agent" && isCursorAgentUiDisabled()) return;

    const previous = chatMode;
    setChatMode(next);
    setSavingChatMode(true);
    setError(null);

    try {
      const updated = await updateWorkspace(workspaceId, { chat_mode: next });
      setChatMode(updated.chat_mode);
      onWorkspaceUpdated?.(updated);
    } catch {
      setChatMode(previous);
      setError("Failed to update chat engine");
    } finally {
      setSavingChatMode(false);
    }
  }

  async function handleToggle(key: ToolKey, next: boolean) {
    if (!settings || savingKey) return;

    const previous = settings;
    setSettings({ ...settings, [key]: next });
    setSavingKey(key);
    setError(null);

    try {
      const updated = await updateToolSettings(workspaceId, { [key]: next });
      setSettings(updated);
    } catch {
      setSettings(previous);
      setError(`Failed to update ${TOOL_META[key].label.toLowerCase()}`);
    } finally {
      setSavingKey(null);
    }
  }

  async function handleSaveGitHubLink() {
    const trimmed = repoUrl.trim();
    if (!trimmed || githubSaving) return;

    setGithubSaving(true);
    setGithubMessage(null);
    try {
      const link = await saveGitHubLink(workspaceId, trimmed);
      setGithubLink(link);
      setRepoUrl(link.repo_url);
      setGithubMessage("GitHub repo linked.");
    } catch (err) {
      setGithubMessage(err instanceof Error ? err.message : "Failed to save GitHub link");
    } finally {
      setGithubSaving(false);
    }
  }

  async function handleSyncGitHub() {
    if (githubSyncing) return;

    setGithubSyncing(true);
    setGithubMessage(null);
    try {
      const result = await syncGitHubRepo(workspaceId);
      setGithubLink((prev) =>
        prev
          ? {
              ...prev,
              repo_full_name: result.repo_full_name,
              default_branch: result.default_branch,
              last_synced_at: result.last_synced_at,
            }
          : prev
      );
      const fileNames = result.synced_files.map((file) => file.filename).join(", ");
      setGithubMessage(
        `Synced ${result.repo_full_name ?? "repo"} - ${fileNames || "no files"}`
      );
    } catch (err) {
      setGithubMessage(err instanceof Error ? err.message : "Failed to sync GitHub repo");
    } finally {
      setGithubSyncing(false);
    }
  }

  const toolKeys: ToolKey[] =
    workspaceType === "code"
      ? ["file_search", "web_search", "memory", "github_read", "code_search"]
      : ["file_search", "web_search", "memory"];

  return (
    <div className="flex h-full min-h-0 flex-col gap-6 overflow-y-auto rounded-2xl border-2 border-foreground/15 bg-card p-4 shadow-sm">
      <div className="shrink-0">
        <div className="flex items-center gap-2">
          <SlidersHorizontal className="size-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold">Agent Tools</h3>
        </div>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">
          Choose chat engine and tool toggles for this workspace. Changes apply on the
          next message.
        </p>
      </div>

      <div className="rounded-2xl border-2 border-foreground/15 bg-background p-4 shadow-sm">
        <div className="flex items-center gap-2">
          <Bot className="size-4 text-muted-foreground" />
          <h4 className="text-sm font-semibold">Chat engine</h4>
        </div>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">
          {isCloudEdition()
            ? "Cloud edition uses LangGraph with Chroma RAG over uploaded files."
            : "LangGraph uses Chroma RAG. Cursor Agent reads uploads/ directly and uses CURSOR_API_KEY on the API server."}
        </p>

        {chatMode === "cursor_agent" && cursorConfigured === false && (
          <div className="mt-3 rounded-xl border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-800 dark:text-amber-300">
            CURSOR_API_KEY is not configured on the backend. Chat will fail until you
            set it in personalops/apps/api/.env and restart the API.
          </div>
        )}

        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          {UI_CHAT_ENGINE_MODES.map((mode) => {
            const meta = CHAT_ENGINE_META[mode];
            const Icon = meta.icon;
            const selected = chatMode === mode;
            const isDisabled =
              mode === "cursor_agent" && isCursorAgentUiDisabled();

            return (
              <div
                key={mode}
                title={isDisabled ? CURSOR_AGENT_DESKTOP_TOOLTIP : undefined}
                className={cn(isDisabled && "cursor-not-allowed")}
              >
                <button
                  type="button"
                  disabled={savingChatMode || isDisabled}
                  onClick={() => handleChatModeChange(mode)}
                  className={cn(
                    "w-full rounded-2xl border-2 p-4 text-left transition-colors",
                    selected
                      ? "border-primary/40 bg-primary/[0.06] shadow-sm"
                      : "border-2 border-foreground/15 bg-card hover:border-foreground/25",
                    (savingChatMode || isDisabled) && "opacity-60",
                    isDisabled && "pointer-events-none"
                  )}
                >
                  <div className="flex items-center gap-2">
                    <div
                      className={cn(
                        "flex size-8 items-center justify-center rounded-lg border",
                        selected
                          ? "border-primary/30 bg-primary/10 text-primary"
                          : "border-foreground/15 bg-muted text-muted-foreground"
                      )}
                    >
                      <Icon className="size-4" />
                    </div>
                    <p className="text-sm font-semibold">{meta.label}</p>
                    {isDisabled && (
                      <span className="ml-auto rounded-full border border-muted-foreground/30 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                        Desktop
                      </span>
                    )}
                    {savingChatMode && selected && (
                      <Loader2 className="ml-auto size-4 animate-spin text-muted-foreground" />
                    )}
                  </div>
                  <p className="mt-2 text-xs leading-5 text-muted-foreground">
                    {isDisabled ? CURSOR_AGENT_DESKTOP_DESCRIPTION : meta.description}
                  </p>
                </button>
              </div>
            );
          })}
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-destructive/20 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" />
          Loading tool settings...
        </div>
      ) : settings ? (
        <div className="space-y-3">
          {toolKeys.map((key) => {
            const meta = TOOL_META[key];
            const Icon = meta.icon;
            const isSaving = savingKey === key;

            return (
              <div
                key={key}
                className={cn(
                  "rounded-2xl border-2 p-4 transition-colors",
                  settings[key]
                    ? "border-primary/35 bg-primary/[0.04] shadow-sm"
                    : "border-2 border-foreground/15 bg-background shadow-sm"
                )}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <div
                        className={cn(
                          "flex size-8 items-center justify-center rounded-lg border",
                          settings[key]
                            ? "border-primary/30 bg-primary/10 text-primary"
                            : "border-foreground/15 bg-muted text-muted-foreground"
                        )}
                      >
                        <Icon className="size-4" />
                      </div>
                      <p className="text-sm font-semibold">{meta.label}</p>
                      {key === "web_search" && settings.web_search && (
                        <span className="inline-flex items-center gap-1 rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[0.65rem] font-medium uppercase tracking-wide text-amber-700 dark:text-amber-300">
                          <AlertTriangle className="size-3" />
                          External query
                        </span>
                      )}
                    </div>
                    <p className="mt-2 text-xs leading-5 text-muted-foreground">
                      {meta.description}
                    </p>
                    {key === "web_search" && (
                      <p className="mt-2 text-xs leading-5 text-amber-700/90 dark:text-amber-300/90">
                        Web search sends your question to an external service (Tavily or
                        DuckDuckGo). Disable it for fully local-only answers.
                      </p>
                    )}
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-1 border-l border-foreground/10 pl-4 pt-0.5">
                    {isSaving && (
                      <Loader2 className="size-4 animate-spin text-muted-foreground" />
                    )}
                    <ToolToggle
                      label={meta.label}
                      checked={settings[key]}
                      disabled={isSaving}
                      onChange={(next) => handleToggle(key, next)}
                    />
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      ) : null}

      {workspaceType === "code" && (
        <div className="rounded-2xl border-2 border-foreground/15 bg-background p-4 shadow-sm">
          <div className="flex items-center gap-2">
            <FolderGit className="size-4 text-muted-foreground" />
            <h4 className="text-sm font-semibold">GitHub (read-only)</h4>
          </div>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            Link a public repo, sync README and open issues into workspace files. No push,
            no PR creation.
          </p>

          {githubLoading ? (
            <div className="mt-3 flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" />
              Loading GitHub link...
            </div>
          ) : (
            <div className="mt-3 space-y-3">
              <input
                type="url"
                value={repoUrl}
                onChange={(e) => setRepoUrl(e.target.value)}
                placeholder="https://github.com/owner/repo"
                className="h-9 w-full rounded-lg border border-input bg-background px-3 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30"
              />
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  size="sm"
                  onClick={handleSaveGitHubLink}
                  disabled={githubSaving || !repoUrl.trim()}
                >
                  {githubSaving ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    "Save link"
                  )}
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={handleSyncGitHub}
                  disabled={githubSyncing || !githubLink}
                >
                  {githubSyncing ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    "Sync README & issues"
                  )}
                </Button>
              </div>
              {githubLink && (
                <div className="rounded-xl border border-foreground/10 bg-muted/20 px-3 py-2 text-xs leading-5 text-muted-foreground">
                  <p>
                    <span className="font-medium text-foreground">
                      {githubLink.repo_full_name ?? githubLink.repo_url}
                    </span>
                    {githubLink.default_branch ? `  -  ${githubLink.default_branch}` : ""}
                  </p>
                  {githubLink.repo_description && <p className="mt-1">{githubLink.repo_description}</p>}
                  <p className="mt-1">Last synced: {formatSyncedAt(githubLink.last_synced_at)}</p>
                </div>
              )}
              {githubMessage && (
                <p className="text-xs text-muted-foreground">{githubMessage}</p>
              )}
            </div>
          )}
        </div>
      )}

      <div className="shrink-0 rounded-2xl border-2 border-dashed border-foreground/20 bg-muted/30 px-4 py-4 text-xs leading-5 text-muted-foreground">
        <p className="font-medium text-foreground">
          {chatMode === "cursor_agent"
            ? "How Cursor Agent uses these toggles"
            : "How LangGraph routing uses these toggles"}
        </p>
        <ul className="mt-2 list-disc space-y-1 pl-4">
          {chatMode === "cursor_agent" ? (
            <>
              <li>
                <span className="text-foreground">File search off</span> - prompt tells
                Agent not to read workspace files.
              </li>
              <li>
                <span className="text-foreground">Web search off</span> - local files
                only; no web fallback after verify.
              </li>
              <li>
                <span className="text-foreground">Memory on</span> - entries inject into
                prompt and sync to{" "}
                <code className="text-foreground">.cursor/rules/personalops-memory.mdc</code>.
              </li>
            </>
          ) : (
            <>
              <li>
                <span className="text-foreground">File search off</span> - agent cannot
                use file_rag or hybrid routes.
              </li>
              <li>
                <span className="text-foreground">Web search off</span> - agent cannot use
                web_search or hybrid routes.
              </li>
              <li>
                <span className="text-foreground">Memory off</span> - Memory tab entries
                are ignored during chat.
              </li>
            </>
          )}
          {workspaceType === "code" && (
            <>
              <li>
                <span className="text-foreground">GitHub read off</span> - synced GitHub
                files are still indexed, but the agent is nudged not to rely on them.
              </li>
              <li>
                <span className="text-foreground">Code search off</span> - skips ripgrep
                line lookup; vector file search still works.
              </li>
            </>
          )}
        </ul>
      </div>
    </div>
  );
}
