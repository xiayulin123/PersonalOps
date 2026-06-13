import { useCallback, useEffect, useState, type ReactNode } from "react";
import {
  Brain,
  FileSearch,
  Files,
  Globe,
  BarChart3,
  LayoutTemplate,
  Loader2,
  MessageSquare,
  SlidersHorizontal,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { LifeConnectionsCard } from "@/components/LifeConnectionsCard";
import {
  fetchWorkspaceOverview,
  type WorkspaceOverview,
} from "@/lib/api";
import type { WorkspaceType } from "@/lib/workspace-types";
import { cn } from "@/lib/utils";

export type WorkspaceNavTab =
  | "overview"
  | "files"
  | "chat"
  | "inbox"
  | "calendar"
  | "memory"
  | "tools"
  | "evaluation";

type OverviewTabProps = {
  workspaceId: string;
  workspaceType: WorkspaceType;
  refreshKey?: number;
  onNavigate: (tab: WorkspaceNavTab) => void;
};

function StatusPill({ status }: { status: string }) {
  return (
    <span
      className={cn(
        "rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
        status === "ready" && "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
        status === "failed" && "bg-destructive/10 text-destructive",
        status === "needs_ocr" && "bg-amber-500/10 text-amber-700 dark:text-amber-300",
        (status === "indexing" || status === "ocr" || status === "pending") &&
          "bg-sky-500/10 text-sky-700 dark:text-sky-300",
        status === "empty" && "bg-muted text-muted-foreground"
      )}
    >
      {status}
    </span>
  );
}

function ToolChip({
  label,
  enabled,
  icon: Icon,
}: {
  label: string;
  enabled: boolean;
  icon: typeof FileSearch;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium",
        enabled
          ? "border-primary/25 bg-primary/10 text-primary"
          : "border-border bg-muted text-muted-foreground"
      )}
    >
      <Icon className="size-3.5" />
      {label}
      <span className="opacity-70">{enabled ? "On" : "Off"}</span>
    </span>
  );
}

function OverviewCard({
  title,
  icon: Icon,
  actionLabel,
  onAction,
  children,
}: {
  title: string;
  icon: typeof Files;
  actionLabel?: string;
  onAction?: () => void;
  children: ReactNode;
}) {
  return (
    <section className="rounded-2xl border-2 border-foreground/15 bg-card p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Icon className="size-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold">{title}</h3>
        </div>
        {actionLabel && onAction && (
          <Button type="button" size="sm" variant="ghost" onClick={onAction}>
            {actionLabel}
          </Button>
        )}
      </div>
      {children}
    </section>
  );
}

export function OverviewTab({
  workspaceId,
  workspaceType,
  refreshKey = 0,
  onNavigate,
}: OverviewTabProps) {
  const [overview, setOverview] = useState<WorkspaceOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadOverview = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchWorkspaceOverview(workspaceId);
      setOverview(data);
    } catch {
      setError("Failed to load overview");
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    loadOverview();
  }, [loadOverview, refreshKey]);

  if (loading) {
    return (
      <div className="flex h-full min-h-[240px] items-center justify-center rounded-2xl border-2 border-foreground/15 bg-card">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" />
          Loading overview...
        </div>
      </div>
    );
  }

  if (error || !overview) {
    return (
      <div className="rounded-2xl border-2 border-destructive/20 bg-destructive/5 p-4 text-sm text-destructive">
        <p>{error ?? "Overview unavailable"}</p>
        <Button type="button" size="sm" variant="outline" className="mt-3" onClick={loadOverview}>
          Retry
        </Button>
      </div>
    );
  }

  const summary = overview.indexing_summary;

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto rounded-2xl border-2 border-foreground/15 bg-card/40 p-4">
      <div className="mb-4">
        <h2 className="text-base font-semibold tracking-tight">Workspace overview</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          Quick snapshot of files, chat, memory, and tools for this {workspaceType} workspace.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {workspaceType === "life" && (
          <LifeConnectionsCard workspaceId={workspaceId} refreshKey={refreshKey} />
        )}

        <OverviewCard
          title="Files"
          icon={Files}
          actionLabel="Open Files"
          onAction={() => onNavigate("files")}
        >
          <div className="mb-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
            <span>{summary.total} total</span>
            <span>· {summary.ready} ready</span>
            {summary.needs_ocr > 0 && <span>· {summary.needs_ocr} needs OCR</span>}
            {summary.failed > 0 && <span>· {summary.failed} failed</span>}
          </div>
          {overview.recent_files.length === 0 ? (
            <p className="text-sm text-muted-foreground">No files uploaded yet.</p>
          ) : (
            <ul className="space-y-2">
              {overview.recent_files.map((file) => (
                <li
                  key={`${file.filename}-${file.status}`}
                  className="flex items-center justify-between gap-2 rounded-xl border border-foreground/10 bg-background px-3 py-2 text-sm"
                >
                  <span className="truncate font-medium">{file.filename}</span>
                  <div className="flex shrink-0 items-center gap-2">
                    <span className="text-xs text-muted-foreground">
                      {file.chunk_count} chunks
                    </span>
                    <StatusPill status={file.status} />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </OverviewCard>

        <OverviewCard
          title="Recent chat"
          icon={MessageSquare}
          actionLabel="Open Chat"
          onAction={() => onNavigate("chat")}
        >
          {overview.recent_messages.length === 0 ? (
            <p className="text-sm text-muted-foreground">No messages yet. Ask a question in Chat.</p>
          ) : (
            <ul className="space-y-2">
              {overview.recent_messages.map((message, index) => (
                <li
                  key={`${message.role}-${index}`}
                  className="rounded-xl border border-foreground/10 bg-background px-3 py-2 text-sm"
                >
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                    {message.role}
                  </p>
                  <p className="mt-1 line-clamp-2 leading-5 text-foreground">
                    {message.content_preview}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </OverviewCard>

        <OverviewCard
          title="Memory"
          icon={Brain}
          actionLabel="Open Memory"
          onAction={() => onNavigate("memory")}
        >
          <p className="text-3xl font-semibold tracking-tight">{overview.memory_count}</p>
          <p className="mt-1 text-sm text-muted-foreground">
            saved preference{overview.memory_count === 1 ? "" : "s"} for the agent
          </p>
        </OverviewCard>

        <OverviewCard
          title="Suggested tasks"
          icon={LayoutTemplate}
          actionLabel="Open Chat"
          onAction={() => onNavigate("chat")}
        >
          {overview.suggested_templates.length === 0 ? (
            <p className="text-sm text-muted-foreground">No templates for this workspace type.</p>
          ) : (
            <ul className="space-y-2">
              {overview.suggested_templates.map((template) => (
                <li
                  key={template.id}
                  className="rounded-xl border border-foreground/10 bg-background px-3 py-2"
                >
                  <p className="text-sm font-medium">{template.label}</p>
                  <p className="mt-0.5 text-xs leading-5 text-muted-foreground">
                    {template.description}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </OverviewCard>

        <OverviewCard
          title="Evaluation"
          icon={BarChart3}
          actionLabel="Open Evaluation"
          onAction={() => onNavigate("evaluation")}
        >
          <p className="text-sm text-muted-foreground">
            Track chat latency, citation rate, route mix, and thumbs feedback for this
            workspace.
          </p>
        </OverviewCard>

        <OverviewCard
          title="Tools"
          icon={SlidersHorizontal}
          actionLabel="Open Tools"
          onAction={() => onNavigate("tools")}
          >
          <div className="flex flex-wrap gap-2">
            <ToolChip
              label="File search"
              enabled={overview.tool_settings.file_search}
              icon={FileSearch}
            />
            <ToolChip
              label="Web search"
              enabled={overview.tool_settings.web_search}
              icon={Globe}
            />
            <ToolChip
              label="Memory"
              enabled={overview.tool_settings.memory}
              icon={Brain}
            />
          </div>
        </OverviewCard>
      </div>
    </div>
  );
}
