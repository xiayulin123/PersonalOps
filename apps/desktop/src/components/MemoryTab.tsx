import { FormEvent, useCallback, useEffect, useState } from "react";
import { Brain, Check, Loader2, Pencil, Sparkles, Trash2, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  adoptAllPersonalizationDrafts,
  adoptPersonalizationDraft,
  createMemory,
  deleteMemory,
  distillPersonalization,
  getPersonalizationSettings,
  getPersonalizationStats,
  listMemory,
  listPersonalizationDrafts,
  rejectPersonalizationDraft,
  updateMemory,
  updatePersonalizationSettings,
  wipePersonalizationData,
  type ChatMode,
  type MemoryRecord,
  type PersonalizationSettings,
  type PersonalizationStats,
} from "@/lib/api";
import type { WorkspaceType } from "@/lib/workspace-types";
import { cn } from "@/lib/utils";

type MemoryTabProps = {
  workspaceId: string;
  workspaceType: WorkspaceType;
  chatMode?: ChatMode;
};

function truncate(text: string, max = 120) {
  if (text.length <= max) return text;
  return `${text.slice(0, max)}...`;
}

function kindLabel(kind?: string) {
  switch (kind) {
    case "rule":
      return "Rule";
    case "habit":
      return "Habit";
    default:
      return "Fact";
  }
}

function ToggleSwitch({
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

export function MemoryTab({
  workspaceId,
  workspaceType,
  chatMode = "langgraph",
}: MemoryTabProps) {
  const isCursorMode = chatMode === "cursor_agent";
  const [items, setItems] = useState<MemoryRecord[]>([]);
  const [drafts, setDrafts] = useState<MemoryRecord[]>([]);
  const [settings, setSettings] = useState<PersonalizationSettings | null>(null);
  const [stats, setStats] = useState<PersonalizationStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [distillMessage, setDistillMessage] = useState<string | null>(null);
  const [key, setKey] = useState("");
  const [value, setValue] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");

  const loadAll = useCallback(async () => {
    try {
      const [memoryData, draftData, settingsData, statsData] = await Promise.all([
        listMemory(workspaceId),
        listPersonalizationDrafts(workspaceId),
        getPersonalizationSettings(workspaceId),
        getPersonalizationStats(workspaceId),
      ]);
      setItems(memoryData);
      setDrafts(draftData);
      setSettings(settingsData);
      setStats(statsData);
      setError(null);
    } catch {
      setError("Failed to load memory");
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    setLoading(true);
    loadAll();
  }, [loadAll]);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    const trimmedKey = key.trim();
    const trimmedValue = value.trim();
    if (!trimmedKey || !trimmedValue || saving) return;

    setSaving(true);
    setError(null);
    try {
      await createMemory(workspaceId, trimmedKey, trimmedValue);
      setKey("");
      setValue("");
      await loadAll();
    } catch {
      setError("Failed to create memory. Key may already exist in this workspace.");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(memoryId: string) {
    setError(null);
    try {
      await deleteMemory(workspaceId, memoryId);
      if (editingId === memoryId) {
        setEditingId(null);
        setEditValue("");
      }
      await loadAll();
    } catch {
      setError("Failed to delete memory");
    }
  }

  function startEdit(item: MemoryRecord) {
    setEditingId(item.id);
    setEditValue(item.value);
  }

  async function handleSaveEdit(memoryId: string) {
    const trimmedValue = editValue.trim();
    if (!trimmedValue) {
      setError("Memory value cannot be empty");
      return;
    }

    setSaving(true);
    setError(null);
    try {
      await updateMemory(workspaceId, memoryId, trimmedValue);
      setEditingId(null);
      setEditValue("");
      await loadAll();
    } catch {
      setError("Failed to update memory");
    } finally {
      setSaving(false);
    }
  }

  async function handleAdoptDraft(memoryId: string) {
    setSaving(true);
    setError(null);
    try {
      await adoptPersonalizationDraft(workspaceId, memoryId);
      await loadAll();
    } catch {
      setError("Failed to adopt learned item");
    } finally {
      setSaving(false);
    }
  }

  async function handleRejectDraft(memoryId: string) {
    setSaving(true);
    setError(null);
    try {
      await rejectPersonalizationDraft(workspaceId, memoryId);
      await loadAll();
    } catch {
      setError("Failed to reject learned item");
    } finally {
      setSaving(false);
    }
  }

  async function handleAdoptAll() {
    setSaving(true);
    setError(null);
    try {
      await adoptAllPersonalizationDrafts(workspaceId);
      await loadAll();
    } catch {
      setError("Failed to adopt all learned items");
    } finally {
      setSaving(false);
    }
  }

  async function handleSettingsToggle(
    field: "auto_learn_enabled" | "require_approval",
    next: boolean
  ) {
    if (!settings) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await updatePersonalizationSettings(workspaceId, { [field]: next });
      setSettings(updated);
      await loadAll();
    } catch {
      setError("Failed to update personalization settings");
    } finally {
      setSaving(false);
    }
  }

  async function handleDistill(period: "day" | "week", force = false) {
    setSaving(true);
    setError(null);
    setDistillMessage(null);
    try {
      const result = await distillPersonalization(workspaceId, period, force);
      if (result.status === "done" && result.written && result.written > 0) {
        const approval = settings?.require_approval;
        setDistillMessage(
          approval
            ? `Distilled ${result.written} item(s). Review them below and tap Adopt.`
            : `Distilled ${result.written} item(s) — now active in memory.`
        );
      } else if (result.skipped) {
        setDistillMessage(`Skipped: ${result.reason ?? result.status}`);
      } else if (result.status === "failed") {
        setError(result.error ?? "Distillation failed");
      } else {
        setDistillMessage(`Distill finished: ${result.status}`);
      }
      await loadAll();
    } catch {
      setError("Distillation failed. Check OPENAI_API_KEY and prompt count.");
    } finally {
      setSaving(false);
    }
  }

  async function handleWipeData() {
    const confirmed = window.confirm(
      "Delete all prompt logs and auto-learned memory for this workspace? Manual memory is kept."
    );
    if (!confirmed) return;

    setSaving(true);
    setError(null);
    try {
      await wipePersonalizationData(workspaceId);
      await loadAll();
    } catch {
      setError("Failed to wipe personalization data");
    } finally {
      setSaving(false);
    }
  }

  const examplesByType: Record<WorkspaceType, { key: string; value: string }[]> = {
    study: [
      { key: "language_preference", value: "Prefer Chinese explanations with bilingual technical terms." },
      { key: "course", value: "ECE457A real-time systems" },
      { key: "explanation_style", value: "Step-by-step with examples." },
    ],
    code: [
      { key: "tech_stack", value: "AWS, Kubernetes, Terraform, React, FastAPI" },
      { key: "explanation_style", value: "Production-style, concise debugging steps." },
    ],
    life: [
      { key: "timezone", value: "America/Toronto (EST/EDT)" },
      { key: "priority_style", value: "Prefer urgent deadlines first, then health errands." },
      { key: "document_categories", value: "Bills, medical, travel, personal goals" },
    ],
    career: [
      { key: "target_role", value: "Software engineering intern / new grad" },
      { key: "resume_tone", value: "Concise bullets with measurable impact." },
      { key: "highlight_skills", value: "Python, React, AWS, distributed systems" },
    ],
  };

  const examples = examplesByType[workspaceType] ?? examplesByType.study;
  const manualItems = items.filter((item) => item.source !== "auto");
  const learnedActive = items.filter((item) => item.source === "auto");

  return (
    <div className="flex h-full min-h-0 flex-col gap-6 overflow-y-auto rounded-2xl border border-border bg-card p-4">
      <div className="shrink-0">
        <div className="flex items-center gap-2">
          <Brain className="size-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold">Workspace Memory</h3>
        </div>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">
          Store preferences the agent can use in chat when memory is enabled in Tools.
          AI-learned habits appear below for review before they affect answers.
        </p>
        {isCursorMode && (
          <div
            className={cn(
              "mt-3 rounded-xl border px-3 py-2 text-xs leading-5",
              "border-violet-500/25 bg-violet-500/8 text-violet-900 dark:text-violet-200"
            )}
          >
            <p className="font-medium">Cursor Agent mode</p>
            <p className="mt-1 text-violet-800/90 dark:text-violet-100/90">
              Active memory is injected into the Cursor Agent prompt and synced to{" "}
              <code className="font-mono text-[0.7rem]">
                uploads/.cursor/rules/personalops-memory.mdc
              </code>
              .
            </p>
          </div>
        )}
      </div>

      {settings && (
        <section className="shrink-0 space-y-3 rounded-2xl border border-border bg-background/60 p-4">
          <div className="flex items-center gap-2">
            <Sparkles className="size-4 text-amber-500" />
            <p className="text-sm font-medium">Personalization settings</p>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="text-sm">Auto-learn from chat</p>
              <p className="text-xs text-muted-foreground">
                Log prompts and distill habits when thresholds are met
              </p>
            </div>
            <ToggleSwitch
              checked={settings.auto_learn_enabled}
              disabled={saving}
              label="Auto-learn from chat"
              onChange={(next) => handleSettingsToggle("auto_learn_enabled", next)}
            />
          </div>
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="text-sm">Require approval</p>
              <p className="text-xs text-muted-foreground">
                Learned items stay pending until you adopt them
              </p>
            </div>
            <ToggleSwitch
              checked={settings.require_approval}
              disabled={saving || !settings.auto_learn_enabled}
              label="Require approval for learned memory"
              onChange={(next) => handleSettingsToggle("require_approval", next)}
            />
          </div>
          {stats && (
            <p className="text-xs text-muted-foreground">
              Today: {stats.today_count}/{stats.daily_threshold} prompts · Week:{" "}
              {stats.week_count}/{stats.weekly_threshold}
              {stats.today_distillation_status !== "pending" && (
                <> · Today distill: {stats.today_distillation_status}</>
              )}
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              size="sm"
              disabled={saving || !settings.auto_learn_enabled}
              onClick={() => handleDistill("day", stats ? stats.today_count >= stats.daily_threshold : false)}
            >
              {saving ? <Loader2 className="size-4 animate-spin" /> : "Distill today"}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={saving || !settings.auto_learn_enabled}
              onClick={() => handleDistill("week", stats ? stats.week_count >= stats.weekly_threshold : false)}
            >
              Distill week
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={saving || !settings.auto_learn_enabled}
              onClick={() => handleDistill("day", true)}
            >
              Force distill today
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            Uses today&apos;s or this week&apos;s logged user prompts only (not full chat
            replies). With Require approval on, results appear in Pending review.
          </p>
          {distillMessage && (
            <p className="text-xs text-emerald-700 dark:text-emerald-300">{distillMessage}</p>
          )}
          {settings.cloud_archive_enabled && (
            <p className="text-xs text-muted-foreground">
              Cloud archive ({settings.cloud_archive_provider}):{" "}
              {settings.cloud_archive_configured ? "configured" : "missing bucket or key in .env"}
            </p>
          )}
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={saving}
            onClick={handleWipeData}
          >
            <Trash2 data-icon="inline-start" />
            Wipe prompt logs &amp; auto memory
          </Button>
        </section>
      )}

      {drafts.length > 0 && (
        <section className="shrink-0 space-y-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-sm font-medium">Learned habits — pending review</p>
              <p className="text-xs text-muted-foreground">
                Adopt to inject into chat; reject to discard permanently.
              </p>
            </div>
            <Button
              type="button"
              size="sm"
              disabled={saving}
              onClick={handleAdoptAll}
            >
              Adopt all
            </Button>
          </div>
          <div className="space-y-3">
            {drafts.map((draft) => (
              <div
                key={draft.id}
                className="rounded-2xl border border-amber-500/30 bg-amber-500/5 p-4"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[0.65rem] font-semibold uppercase tracking-wide text-amber-800 dark:text-amber-200">
                    {kindLabel(draft.kind)}
                  </span>
                  <span className="text-sm font-medium">{draft.key}</span>
                  {typeof draft.confidence === "number" && (
                    <span className="text-xs text-muted-foreground">
                      {Math.round(draft.confidence * 100)}% confidence
                    </span>
                  )}
                  {draft.period_start && (
                    <span className="text-xs text-muted-foreground">
                      from {draft.period_start}
                    </span>
                  )}
                </div>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">
                  {truncate(draft.value, 240)}
                </p>
                <div className="mt-3 flex gap-2">
                  <Button
                    type="button"
                    size="sm"
                    disabled={saving}
                    onClick={() => handleAdoptDraft(draft.id)}
                  >
                    <Check data-icon="inline-start" />
                    Adopt
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={saving}
                    onClick={() => handleRejectDraft(draft.id)}
                  >
                    <X data-icon="inline-start" />
                    Reject
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      <form onSubmit={handleCreate} className="shrink-0 space-y-3 rounded-2xl border border-border bg-background/60 p-4">
        <p className="text-sm font-medium">Add manual memory</p>
        <input
          value={key}
          onChange={(e) => setKey(e.target.value)}
          placeholder="Key, e.g. language_preference"
          className="w-full rounded-xl border border-input bg-background px-3 py-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30"
        />
        <textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Value, e.g. User prefers Chinese explanations..."
          rows={3}
          className="w-full resize-none rounded-xl border border-input bg-background px-3 py-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30"
        />
        <Button type="submit" disabled={saving || !key.trim() || !value.trim()}>
          {saving ? <Loader2 className="size-4 animate-spin" /> : "Save memory"}
        </Button>
      </form>

      {error && (
        <div className="rounded-xl border border-destructive/20 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" />
          Loading memory...
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border px-4 py-6">
          <p className="text-sm font-medium">No active memory yet</p>
          <p className="mt-2 text-xs leading-5 text-muted-foreground">
            Examples for {workspaceType} workspaces:
          </p>
          <ul className="mt-3 space-y-2 text-xs text-muted-foreground">
            {examples.map((example) => (
              <li key={example.key} className="rounded-xl bg-muted/40 px-3 py-2">
                <span className="font-medium text-foreground">{example.key}</span>
                <span className="text-muted-foreground"> — {example.value}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <div className="space-y-6">
          {manualItems.length > 0 && (
            <section className="space-y-3">
              <p className="text-sm font-medium">Active memory (manual)</p>
              {manualItems.map((item) => (
                <MemoryCard
                  key={item.id}
                  item={item}
                  editingId={editingId}
                  editValue={editValue}
                  saving={saving}
                  canEdit
                  onStartEdit={startEdit}
                  onEditValueChange={setEditValue}
                  onSaveEdit={handleSaveEdit}
                  onDelete={handleDelete}
                />
              ))}
            </section>
          )}
          {learnedActive.length > 0 && (
            <section className="space-y-3">
              <p className="text-sm font-medium">Active memory (learned)</p>
              {learnedActive.map((item) => (
                <MemoryCard
                  key={item.id}
                  item={item}
                  editingId={editingId}
                  editValue={editValue}
                  saving={saving}
                  canEdit={false}
                  onStartEdit={startEdit}
                  onEditValueChange={setEditValue}
                  onSaveEdit={handleSaveEdit}
                  onDelete={handleDelete}
                />
              ))}
            </section>
          )}
        </div>
      )}
    </div>
  );
}

function MemoryCard({
  item,
  editingId,
  editValue,
  saving,
  canEdit,
  onStartEdit,
  onEditValueChange,
  onSaveEdit,
  onDelete,
}: {
  item: MemoryRecord;
  editingId: string | null;
  editValue: string;
  saving: boolean;
  canEdit: boolean;
  onStartEdit: (item: MemoryRecord) => void;
  onEditValueChange: (value: string) => void;
  onSaveEdit: (memoryId: string) => void;
  onDelete: (memoryId: string) => void;
}) {
  return (
    <div className="rounded-2xl border border-border bg-background/60 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            {item.source === "auto" && (
              <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[0.65rem] font-semibold uppercase tracking-wide text-primary">
                Learned
              </span>
            )}
            {item.kind && item.kind !== "memory" && (
              <span className="text-[0.65rem] font-semibold uppercase tracking-wide text-muted-foreground">
                {kindLabel(item.kind)}
              </span>
            )}
            <p className="text-sm font-medium">{item.key}</p>
          </div>
          {editingId === item.id ? (
            <textarea
              value={editValue}
              onChange={(e) => onEditValueChange(e.target.value)}
              rows={3}
              className="mt-2 w-full resize-none rounded-xl border border-input bg-background px-3 py-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30"
            />
          ) : (
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              {truncate(item.value)}
            </p>
          )}
        </div>
        <div className="flex shrink-0 gap-2">
          {canEdit &&
            (editingId === item.id ? (
              <Button
                type="button"
                size="sm"
                disabled={saving}
                onClick={() => onSaveEdit(item.id)}
              >
                Save
              </Button>
            ) : (
              <Button type="button" size="sm" variant="outline" onClick={() => onStartEdit(item)}>
                <Pencil data-icon="inline-start" />
                Edit
              </Button>
            ))}
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => onDelete(item.id)}
          >
            <Trash2 data-icon="inline-start" />
            Delete
          </Button>
        </div>
      </div>
    </div>
  );
}
