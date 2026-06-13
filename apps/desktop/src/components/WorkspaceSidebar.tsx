import { FormEvent, useCallback, useEffect, useState } from "react";
import { FolderKanban, Loader2, Plus, RefreshCw, Trash2, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  createWorkspace,
  deleteWorkspace,
  listWorkspaces,
  type Workspace,
} from "@/lib/api";
import { confirmDestructive } from "@/lib/platform";
import {
  WORKSPACE_TYPES,
  WORKSPACE_TYPE_META,
  getWorkspaceMeta,
  type WorkspaceType,
} from "@/lib/workspace-types";
import { cn } from "@/lib/utils";

type WorkspaceSidebarProps = {
  onSelect: (workspace: Workspace) => void;
  onWorkspaceDeleted?: (workspaceId: string) => void;
  refreshKey?: number;
  onRefresh?: () => void;
};

export function WorkspaceSidebar({
  onSelect,
  onWorkspaceDeleted,
  refreshKey = 0,
  onRefresh,
}: WorkspaceSidebarProps) {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [type, setType] = useState<WorkspaceType>("study");
  const [creating, setCreating] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);

  const loadWorkspaces = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listWorkspaces();
      setWorkspaces(data);
    } catch {
      setError("Failed to load workspaces");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadWorkspaces();
  }, [loadWorkspaces, refreshKey]);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;

    setCreating(true);
    setError(null);
    try {
      const created = await createWorkspace(trimmed, type);
      await loadWorkspaces();
      setActiveId(created.id);
      onSelect(created);
      setName("");
      setType("study");
      setShowForm(false);
    } catch {
      setError("Failed to create workspace");
    } finally {
      setCreating(false);
    }
  }

  function handleSelect(workspace: Workspace) {
    setActiveId(workspace.id);
    onSelect(workspace);
  }

  async function handleDelete(workspace: Workspace) {
    const confirmed = await confirmDestructive(
      `Delete "${workspace.name}"? This removes files, chats, vectors, and watchers. This cannot be undone.`,
      "Delete workspace"
    );
    if (!confirmed) return;

    setDeletingId(workspace.id);
    setError(null);
    try {
      await deleteWorkspace(workspace.id);
      if (activeId === workspace.id) {
        setActiveId(null);
        onWorkspaceDeleted?.(workspace.id);
      }
      await loadWorkspaces();
    } catch {
      setError("Failed to delete workspace");
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <aside className="flex h-full w-72 shrink-0 flex-col border-r border-border bg-sidebar text-sidebar-foreground">
      <div className="border-b border-sidebar-border px-4 py-5">
        <div className="flex items-center gap-2.5">
          <div className="flex size-9 items-center justify-center rounded-xl bg-sidebar-primary text-sidebar-primary-foreground">
            <FolderKanban className="size-4" />
          </div>
          <div>
            <p className="text-sm font-semibold tracking-tight">PersonalOps</p>
            <p className="text-xs text-muted-foreground">Local AI workspace</p>
          </div>
        </div>
      </div>

      <div className="flex items-center justify-between px-4 pt-4">
        <div>
          <h2 className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
            Workspaces
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">
            {workspaces.length} total
          </p>
        </div>
        <Button
          type="button"
          size="sm"
          variant={showForm ? "secondary" : "default"}
          onClick={() => setShowForm((prev) => !prev)}
        >
          {showForm ? (
            <>
              <X data-icon="inline-start" />
              Close
            </>
          ) : (
            <>
              <Plus data-icon="inline-start" />
              New
            </>
          )}
        </Button>
      </div>

      {showForm && (
        <form
          onSubmit={handleCreate}
          className="mx-4 mt-4 space-y-4 rounded-2xl border border-sidebar-border bg-background p-4 shadow-sm"
        >
          <div className="space-y-1.5">
            <label htmlFor="workspace-name" className="text-xs font-medium text-foreground">
              Name
            </label>
            <input
              id="workspace-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="My workspace"
              className="h-9 w-full rounded-lg border border-input bg-background px-3 text-sm text-foreground shadow-xs outline-none transition-colors placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30"
            />
          </div>

          <div className="space-y-2">
            <p className="text-xs font-medium text-foreground">Type</p>
            <div className="grid grid-cols-2 gap-2">
              {WORKSPACE_TYPES.map((option) => {
                const meta = WORKSPACE_TYPE_META[option];
                const Icon = meta.icon;
                const selected = type === option;

                return (
                  <button
                    key={option}
                    type="button"
                    onClick={() => setType(option)}
                    className={cn(
                      "rounded-xl border px-3 py-2.5 text-left transition-all",
                      selected
                        ? "border-primary bg-primary/5 text-foreground ring-1 ring-primary/15"
                        : "border-border bg-background text-muted-foreground hover:border-primary/30 hover:text-foreground"
                    )}
                  >
                    <Icon className="mb-2 size-4" />
                    <div className="text-sm font-medium">{meta.label}</div>
                    <div className="mt-0.5 text-[11px] leading-4 opacity-80">
                      {meta.description}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          <Button type="submit" className="w-full" disabled={creating || !name.trim()}>
            {creating ? (
              <>
                <Loader2 className="size-4 animate-spin" data-icon="inline-start" />
                Creating...
              </>
            ) : (
              "Create workspace"
            )}
          </Button>
        </form>
      )}

      <div className="flex-1 overflow-y-auto px-3 py-4">
        {loading && (
          <div className="flex items-center gap-2 px-2 py-3 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
            Loading workspaces...
          </div>
        )}

        {error && (
          <div className="space-y-2 rounded-xl border border-destructive/20 bg-destructive/5 px-3 py-2 text-sm text-destructive">
            <p>{error}</p>
            {onRefresh && (
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="w-full"
                onClick={onRefresh}
                disabled={loading}
              >
                {loading ? (
                  <Loader2 className="size-3.5 animate-spin" data-icon="inline-start" />
                ) : (
                  <RefreshCw data-icon="inline-start" className="size-3.5" />
                )}
                Retry
              </Button>
            )}
          </div>
        )}

        {!loading && !error && workspaces.length === 0 && (
          <div className="rounded-2xl border border-dashed border-sidebar-border px-4 py-8 text-center">
            <FolderKanban className="mx-auto mb-3 size-8 text-muted-foreground/70" />
            <p className="text-sm font-medium text-foreground">No workspaces yet</p>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">
              Create a study, code, life, or career workspace to get started.
            </p>
          </div>
        )}

        <ul className="space-y-2">
          {workspaces.map((workspace) => {
            const meta = getWorkspaceMeta(workspace.type);
            const Icon = meta.icon;
            const selected = activeId === workspace.id;

            return (
              <li key={workspace.id}>
                <div
                  className={cn(
                    "group flex w-full items-start gap-2 rounded-2xl border px-3 py-3 transition-all",
                    selected
                      ? "border-primary/30 bg-primary/5 shadow-sm"
                      : "border-transparent hover:border-sidebar-border hover:bg-sidebar-accent/70"
                  )}
                >
                  <button
                    type="button"
                    onClick={() => handleSelect(workspace)}
                    className="flex min-w-0 flex-1 items-start gap-3 text-left"
                  >
                    <div
                      className={cn(
                        "mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-xl",
                        selected
                          ? "bg-primary text-primary-foreground"
                          : "bg-muted text-muted-foreground group-hover:text-foreground"
                      )}
                    >
                      <Icon className="size-4" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium text-foreground">
                        {workspace.name}
                      </div>
                      <div className="mt-1 flex items-center gap-2">
                        <span
                          className={cn(
                            "rounded-full px-2 py-0.5 text-[11px] font-medium",
                            selected
                              ? "bg-primary/10 text-primary"
                              : "bg-muted text-muted-foreground"
                          )}
                        >
                          {meta.label}
                        </span>
                      </div>
                    </div>
                  </button>
                  <button
                    type="button"
                    aria-label={`Delete ${workspace.name}`}
                    disabled={deletingId === workspace.id}
                    onClick={() => void handleDelete(workspace)}
                    className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg text-muted-foreground opacity-0 transition-all hover:bg-destructive/10 hover:text-destructive group-hover:opacity-100 disabled:opacity-50"
                  >
                    {deletingId === workspace.id ? (
                      <Loader2 className="size-3.5 animate-spin" />
                    ) : (
                      <Trash2 className="size-3.5" />
                    )}
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      </div>
    </aside>
  );
}
