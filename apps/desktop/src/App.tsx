import { useEffect, useState } from "react";
import {
  BarChart3,
  Bot,
  Brain,
  Calendar,
  Files,
  GraduationCap,
  KeyRound,
  LayoutDashboard,
  Loader2,
  LogOut,
  Mail,
  MessageSquare,
  SlidersHorizontal,
  Sparkles,
} from "lucide-react";

import { BackendStatus } from "@/components/BackendStatus";
import { ChatTab } from "@/components/ChatTab";
import { LoginPage } from "@/components/LoginPage";
import { SplashScreen } from "@/components/SplashScreen";
import { FilesTab } from "@/components/FilesTab";
import { MemoryTab } from "@/components/MemoryTab";
import { EvalDashboard } from "@/components/EvalDashboard";
import { OverviewTab, type WorkspaceNavTab } from "@/components/OverviewTab";
import { LifeCalendarTab } from "@/components/LifeCalendarTab";
import { LifeInboxTab } from "@/components/LifeInboxTab";
import { StudyTab } from "@/components/StudyTab";
import { ToolsTab } from "@/components/ToolsTab";
import { SettingsPage } from "@/components/SettingsPage";
import { WorkspaceSidebar } from "@/components/WorkspaceSidebar";
import type { AuthUser, Workspace } from "@/lib/api";
import { fetchAuthMe, logoutAuth } from "@/lib/api";
import { clearAuthSession, getAuthToken } from "@/lib/auth";
import { CURSOR_AGENT_DESKTOP_TOOLTIP, isCloudEdition } from "@/lib/edition";
import { getWorkspaceMeta } from "@/lib/workspace-types";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

type Tab = WorkspaceNavTab;

function WorkspaceEmptyState() {
  return (
    <div className="flex h-full min-h-[420px] flex-col items-center justify-center rounded-3xl border border-dashed border-border bg-card/40 px-6 text-center">
      <div className="mb-4 flex size-14 items-center justify-center rounded-2xl bg-muted">
        <Files className="size-7 text-muted-foreground" />
      </div>
      <h2 className="text-lg font-semibold tracking-tight">Select a workspace</h2>
      <p className="mt-2 max-w-md text-sm leading-6 text-muted-foreground">
        Choose a workspace from the sidebar, or create a study, code, life, or
        career workspace to get started.
      </p>
    </div>
  );
}

type WorkspaceContentProps = {
  workspace: Workspace;
  refreshKey: number;
  onRefresh: () => void;
  onWorkspaceUpdated: (workspace: Workspace) => void;
};

function WorkspaceContent({
  workspace,
  refreshKey,
  onRefresh,
  onWorkspaceUpdated,
}: WorkspaceContentProps) {
  const [tab, setTab] = useState<Tab>("overview");
  const workspaceMeta = getWorkspaceMeta(workspace.type);

  useEffect(() => {
    setTab("overview");
  }, [workspace.id]);
  const Icon = workspaceMeta.icon;

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2">
      <div className="flex shrink-0 items-center justify-between gap-3 rounded-2xl border border-border bg-card px-3 py-2 shadow-sm">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground">
            <Icon className="size-4" />
          </div>
          <div className="min-w-0">
            <h1 className="truncate text-base font-semibold tracking-tight">
              {workspace.name}
            </h1>
            <p className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <span className="capitalize">{workspace.type} workspace</span>
              <span
                title={
                  workspace.chat_mode === "cursor_agent" && isCloudEdition()
                    ? CURSOR_AGENT_DESKTOP_TOOLTIP
                    : undefined
                }
                className={cn(
                  "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
                  workspace.chat_mode === "cursor_agent" && isCloudEdition()
                    ? "border-muted-foreground/35 bg-muted/50 text-muted-foreground"
                    : workspace.chat_mode === "cursor_agent"
                      ? "border-violet-500/30 bg-violet-500/10 text-violet-700 dark:text-violet-300"
                      : "border-primary/25 bg-primary/10 text-primary"
                )}
              >
                {workspace.chat_mode === "cursor_agent" && !isCloudEdition() ? (
                  <Bot className="size-3" />
                ) : (
                  <Sparkles className="size-3" />
                )}
                {workspace.chat_mode === "cursor_agent" && isCloudEdition()
                  ? "Cursor Agent · Desktop"
                  : workspace.chat_mode === "cursor_agent"
                    ? "Cursor Agent"
                    : "LangGraph"}
              </span>
            </p>
          </div>
        </div>
        <BackendStatus refreshKey={refreshKey} onRefresh={onRefresh} />
      </div>

      <div className="flex shrink-0 gap-1 border-b border-border">
        <button
          type="button"
          onClick={() => setTab("overview")}
          className={cn(
            "inline-flex items-center gap-2 border-b-2 px-3 py-1.5 text-sm font-medium transition-colors",
            tab === "overview"
              ? "border-primary text-foreground"
              : "border-transparent text-muted-foreground hover:text-foreground"
          )}
        >
          <LayoutDashboard className="size-4" />
          Overview
        </button>
        <button
          type="button"
          onClick={() => setTab("files")}
          className={cn(
            "inline-flex items-center gap-2 border-b-2 px-3 py-1.5 text-sm font-medium transition-colors",
            tab === "files"
              ? "border-primary text-foreground"
              : "border-transparent text-muted-foreground hover:text-foreground"
          )}
        >
          <Files className="size-4" />
          Files
        </button>
        <button
          type="button"
          onClick={() => setTab("chat")}
          className={cn(
            "inline-flex items-center gap-2 border-b-2 px-3 py-1.5 text-sm font-medium transition-colors",
            tab === "chat"
              ? "border-primary text-foreground"
              : "border-transparent text-muted-foreground hover:text-foreground"
          )}
        >
          <MessageSquare className="size-4" />
          Chat
        </button>
        {workspace.type === "study" && (
          <button
            type="button"
            onClick={() => setTab("study")}
            className={cn(
              "inline-flex items-center gap-2 border-b-2 px-3 py-1.5 text-sm font-medium transition-colors",
              tab === "study"
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            <GraduationCap className="size-4" />
            Study
          </button>
        )}
        {workspace.type === "life" && (
          <>
            <button
              type="button"
              onClick={() => setTab("inbox")}
              className={cn(
                "inline-flex items-center gap-2 border-b-2 px-3 py-1.5 text-sm font-medium transition-colors",
                tab === "inbox"
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              )}
            >
              <Mail className="size-4" />
              Inbox
            </button>
            <button
              type="button"
              onClick={() => setTab("calendar")}
              className={cn(
                "inline-flex items-center gap-2 border-b-2 px-3 py-1.5 text-sm font-medium transition-colors",
                tab === "calendar"
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              )}
            >
              <Calendar className="size-4" />
              Calendar
            </button>
          </>
        )}
        <button
          type="button"
          onClick={() => setTab("memory")}
          className={cn(
            "inline-flex items-center gap-2 border-b-2 px-3 py-1.5 text-sm font-medium transition-colors",
            tab === "memory"
              ? "border-primary text-foreground"
              : "border-transparent text-muted-foreground hover:text-foreground"
          )}
        >
          <Brain className="size-4" />
          Memory
        </button>
        <button
          type="button"
          onClick={() => setTab("tools")}
          className={cn(
            "inline-flex items-center gap-2 border-b-2 px-3 py-1.5 text-sm font-medium transition-colors",
            tab === "tools"
              ? "border-primary text-foreground"
              : "border-transparent text-muted-foreground hover:text-foreground"
          )}
        >
          <SlidersHorizontal className="size-4" />
          Tools
        </button>
        <button
          type="button"
          onClick={() => setTab("evaluation")}
          className={cn(
            "inline-flex items-center gap-2 border-b-2 px-3 py-1.5 text-sm font-medium transition-colors",
            tab === "evaluation"
              ? "border-primary text-foreground"
              : "border-transparent text-muted-foreground hover:text-foreground"
          )}
        >
          <BarChart3 className="size-4" />
          Evaluation
        </button>
      </div>

      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
        {tab === "overview" ? (
          <OverviewTab
            workspaceId={workspace.id}
            workspaceType={workspace.type}
            refreshKey={refreshKey}
            onNavigate={setTab}
          />
        ) : tab === "files" ? (
          <FilesTab workspaceId={workspace.id} />
        ) : tab === "chat" ? (
          <ChatTab
            workspaceId={workspace.id}
            chatMode={workspace.chat_mode ?? "langgraph"}
          />
        ) : tab === "study" ? (
          <StudyTab
            workspaceId={workspace.id}
            onNavigateToFiles={() => setTab("files")}
          />
        ) : tab === "inbox" ? (
          <LifeInboxTab
            workspaceId={workspace.id}
            refreshKey={refreshKey}
            onNavigate={setTab}
          />
        ) : tab === "calendar" ? (
          <LifeCalendarTab
            workspaceId={workspace.id}
            refreshKey={refreshKey}
            onNavigate={setTab}
          />
        ) : tab === "memory" ? (
          <MemoryTab
            workspaceId={workspace.id}
            workspaceType={workspace.type}
            chatMode={workspace.chat_mode ?? "langgraph"}
          />
        ) : tab === "tools" ? (
          <ToolsTab workspace={workspace} onWorkspaceUpdated={onWorkspaceUpdated} />
        ) : (
          <EvalDashboard workspaceId={workspace.id} refreshKey={refreshKey} />
        )}
      </div>
    </div>
  );
}

function App() {
  const requiresAuth = isCloudEdition();
  const [authUser, setAuthUser] = useState<AuthUser | null>(null);
  const [authLoading, setAuthLoading] = useState(requiresAuth);
  const [selected, setSelected] = useState<Workspace | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [showSplash, setShowSplash] = useState(!requiresAuth);
  const [appRevealed, setAppRevealed] = useState(requiresAuth);

  useEffect(() => {
    if (!requiresAuth) {
      setAuthLoading(false);
      return;
    }
    const token = getAuthToken();
    if (!token) {
      setAuthLoading(false);
      return;
    }
    fetchAuthMe()
      .then((user) => setAuthUser(user))
      .catch(() => {
        clearAuthSession();
        setAuthUser(null);
      })
      .finally(() => setAuthLoading(false));
  }, [requiresAuth]);

  function handleRefresh() {
    setRefreshKey((key) => key + 1);
  }

  async function handleLogout() {
    try {
      await logoutAuth();
    } catch {
      // ignore
    }
    clearAuthSession();
    setAuthUser(null);
    setSelected(null);
  }

  function handleSplashExitStart() {
    setAppRevealed(true);
  }

  function handleSplashComplete() {
    setShowSplash(false);
  }

  if (requiresAuth && authLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <Loader2 className="size-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (requiresAuth && !authUser) {
    return <LoginPage onAuthenticated={setAuthUser} />;
  }

  return (
    <>
      {showSplash && (
        <SplashScreen
          onExitStart={handleSplashExitStart}
          onComplete={handleSplashComplete}
        />
      )}

      <div
        className={cn(
          "flex h-screen bg-background text-foreground",
          appRevealed && "app-shell-enter"
        )}
      >
      <WorkspaceSidebar
        onSelect={(workspace) => {
          setSelected(workspace);
          setShowSettings(false);
        }}
        onWorkspaceDeleted={() => setSelected(null)}
        refreshKey={refreshKey}
        onRefresh={handleRefresh}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        {requiresAuth && authUser && (
          <div className="flex shrink-0 items-center justify-end gap-2 border-b border-border px-4 py-2 text-xs text-muted-foreground">
            <span className="truncate">{authUser.email}</span>
            <Button
              type="button"
              size="sm"
              variant={showSettings ? "secondary" : "ghost"}
              onClick={() => {
                setShowSettings((open) => !open);
                if (!showSettings) setSelected(null);
              }}
            >
              <KeyRound className="size-4" />
              Settings
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => void handleLogout()}>
              <LogOut className="size-4" />
              Sign out
            </Button>
          </div>
        )}
        {!selected && (
          <header className="flex shrink-0 items-center justify-between border-b border-border px-6 py-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                PersonalOps
              </p>
              <p className="text-sm text-muted-foreground">Files & Chat</p>
            </div>
            <BackendStatus refreshKey={refreshKey} onRefresh={handleRefresh} />
          </header>
        )}

        <main
          className={cn(
            "flex min-h-0 flex-1 flex-col overflow-hidden",
            selected || showSettings ? "p-3" : "p-6"
          )}
        >
          {showSettings ? (
            <SettingsPage
              onClose={() => setShowSettings(false)}
              isDemo={Boolean(authUser?.is_demo)}
            />
          ) : selected ? (
            <WorkspaceContent
              workspace={selected}
              refreshKey={refreshKey}
              onRefresh={handleRefresh}
              onWorkspaceUpdated={setSelected}
            />
          ) : (
            <WorkspaceEmptyState />
          )}
        </main>
      </div>
    </div>
    </>
  );
}

export default App;
