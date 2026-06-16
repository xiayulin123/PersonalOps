import { useState } from "react";
import { Check, Loader2, Maximize2, Minimize2, Pencil, Trash2, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  deleteStudyConcept,
  patchStudyConcept,
  type StudyConcept,
  type StudyMastery,
} from "@/lib/api";
import { cn } from "@/lib/utils";

type ConceptCardProps = {
  workspaceId: string;
  concept: StudyConcept;
  onUpdated: (concept: StudyConcept) => void;
  onDeleted: (conceptId: string) => void;
  /** Larger typography for full-page study output view */
  layout?: "default" | "full";
};

const MASTERY_OPTIONS: Array<{ value: StudyMastery; label: string }> = [
  { value: "learning", label: "Learning" },
  { value: "reviewing", label: "Reviewing" },
  { value: "mastered", label: "Mastered" },
];

const MASTERY_STYLES: Record<StudyMastery, string> = {
  learning: "border-sky-500/30 bg-sky-500/10 text-sky-800 dark:text-sky-200",
  reviewing: "border-amber-500/30 bg-amber-500/10 text-amber-900 dark:text-amber-200",
  mastered: "border-emerald-500/30 bg-emerald-500/10 text-emerald-800 dark:text-emerald-200",
};

function ConceptCardBody({
  concept,
  editing,
  titleDraft,
  summaryDraft,
  onTitleChange,
  onSummaryChange,
  large,
}: {
  concept: StudyConcept;
  editing: boolean;
  titleDraft: string;
  summaryDraft: string;
  onTitleChange: (value: string) => void;
  onSummaryChange: (value: string) => void;
  large?: boolean;
}) {
  if (editing) {
    return (
      <div className="min-w-0 flex-1 space-y-2">
        <input
          value={titleDraft}
          onChange={(event) => onTitleChange(event.target.value)}
          className={cn(
            "w-full rounded-lg border border-border bg-background px-3 py-2 font-semibold",
            large ? "text-lg" : "text-sm"
          )}
        />
        <textarea
          value={summaryDraft}
          onChange={(event) => onSummaryChange(event.target.value)}
          rows={large ? 10 : 4}
          className={cn(
            "w-full rounded-lg border border-border bg-background px-3 py-2",
            large ? "text-base" : "text-sm"
          )}
        />
      </div>
    );
  }

  return (
    <div className="min-w-0 flex-1">
      <h3
        className={cn(
          "font-semibold leading-snug",
          large ? "text-xl md:text-2xl" : "text-base"
        )}
      >
        {concept.title}
      </h3>
      <p
        className={cn(
          "mt-2 whitespace-pre-wrap text-muted-foreground",
          large ? "text-base leading-relaxed md:text-lg" : "text-sm"
        )}
      >
        {concept.summary}
      </p>
    </div>
  );
}

export function ConceptCard({
  workspaceId,
  concept,
  onUpdated,
  onDeleted,
  layout = "default",
}: ConceptCardProps) {
  const isFullLayout = layout === "full";
  const [editing, setEditing] = useState(false);
  const [cardExpanded, setCardExpanded] = useState(false);
  const [titleDraft, setTitleDraft] = useState(concept.title);
  const [summaryDraft, setSummaryDraft] = useState(concept.summary);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [masterySaving, setMasterySaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const showLarge = isFullLayout || cardExpanded;

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const updated = await patchStudyConcept(workspaceId, concept.id, {
        title: titleDraft.trim(),
        summary: summaryDraft,
      });
      onUpdated(updated);
      setEditing(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save concept");
    } finally {
      setSaving(false);
    }
  }

  async function handleMasteryChange(next: StudyMastery) {
    if (next === concept.mastery) return;
    setMasterySaving(true);
    setError(null);
    try {
      const updated = await patchStudyConcept(workspaceId, concept.id, {
        mastery: next,
      });
      onUpdated(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update mastery");
    } finally {
      setMasterySaving(false);
    }
  }

  async function handleDelete() {
    if (!window.confirm(`Delete "${concept.title}"?`)) return;
    setDeleting(true);
    setError(null);
    try {
      await deleteStudyConcept(workspaceId, concept.id);
      onDeleted(concept.id);
      setCardExpanded(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete concept");
    } finally {
      setDeleting(false);
    }
  }

  function cancelEdit() {
    setTitleDraft(concept.title);
    setSummaryDraft(concept.summary);
    setEditing(false);
    setError(null);
  }

  function renderDetails() {
    return (
      <>
        {concept.key_points.length > 0 && !editing && (
          <ul
            className={cn(
              "mb-3 list-disc space-y-1.5 pl-5",
              showLarge ? "text-base md:text-lg" : "text-sm"
            )}
          >
            {concept.key_points.map((point) => (
              <li key={point}>{point}</li>
            ))}
          </ul>
        )}

        {concept.example && !editing && (
          <p
            className={cn(
              "mb-3 rounded-xl bg-muted/40 px-3 py-2",
              showLarge ? "text-base md:text-lg" : "text-sm"
            )}
          >
            <span className="font-medium">Example: </span>
            {concept.example}
          </p>
        )}

        <div className="flex flex-wrap items-center gap-2">
          {MASTERY_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              disabled={masterySaving}
              onClick={() => void handleMasteryChange(option.value)}
              className={cn(
                "rounded-full border px-2.5 py-1 text-xs font-medium transition-colors",
                concept.mastery === option.value
                  ? MASTERY_STYLES[option.value]
                  : "border-border text-muted-foreground hover:text-foreground"
              )}
            >
              {option.label}
            </button>
          ))}
        </div>

        {concept.sources.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {concept.sources.map((source, index) => (
              <span
                key={`${source.filename}-${source.page}-${index}`}
                className="rounded-full border border-border px-2 py-0.5 text-[11px] text-muted-foreground"
              >
                {source.filename}
                {source.page > 0 ? ` · p.${source.page}` : ""}
              </span>
            ))}
          </div>
        )}

        {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
      </>
    );
  }

  function renderToolbar() {
    return (
      <div className="flex shrink-0 items-center gap-1">
        {editing ? (
          <>
            <Button
              type="button"
              size="icon-sm"
              variant="ghost"
              onClick={cancelEdit}
              disabled={saving}
            >
              <X className="size-4" />
            </Button>
            <Button
              type="button"
              size="icon-sm"
              variant="ghost"
              onClick={handleSave}
              disabled={saving || !titleDraft.trim()}
            >
              {saving ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Check className="size-4" />
              )}
            </Button>
          </>
        ) : (
          <>
            {!isFullLayout && (
              <Button
                type="button"
                size="icon-sm"
                variant="ghost"
                onClick={() => setCardExpanded(true)}
                title="Expand this concept"
              >
                <Maximize2 className="size-4" />
              </Button>
            )}
            <Button
              type="button"
              size="icon-sm"
              variant="ghost"
              onClick={() => setEditing(true)}
            >
              <Pencil className="size-4" />
            </Button>
            <Button
              type="button"
              size="icon-sm"
              variant="ghost"
              onClick={handleDelete}
              disabled={deleting}
            >
              {deleting ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Trash2 className="size-4" />
              )}
            </Button>
          </>
        )}
      </div>
    );
  }

  const article = (
    <article
      className={cn(
        "rounded-2xl border-2 border-foreground/10 bg-card shadow-sm",
        showLarge ? "p-6 md:p-8" : "p-4"
      )}
    >
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <ConceptCardBody
          concept={concept}
          editing={editing}
          titleDraft={titleDraft}
          summaryDraft={summaryDraft}
          onTitleChange={setTitleDraft}
          onSummaryChange={setSummaryDraft}
          large={showLarge}
        />
        {renderToolbar()}
      </div>
      {renderDetails()}
    </article>
  );

  if (isFullLayout) {
    return article;
  }

  return (
    <>
      {article}
      {cardExpanded && (
        <div className="fixed inset-0 z-[60] flex flex-col bg-background">
          <div className="flex items-center justify-between border-b border-border px-4 py-3 md:px-6">
            <p className="text-sm font-medium text-muted-foreground">Concept detail</p>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => setCardExpanded(false)}
            >
              <Minimize2 className="size-4" />
              Minimize
            </Button>
          </div>
          <div className="flex-1 overflow-y-auto px-4 py-5 md:px-8 md:py-6">
            <div className="mx-auto max-w-3xl">
              <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
                <ConceptCardBody
                  concept={concept}
                  editing={editing}
                  titleDraft={titleDraft}
                  summaryDraft={summaryDraft}
                  onTitleChange={setTitleDraft}
                  onSummaryChange={setSummaryDraft}
                  large
                />
                {renderToolbar()}
              </div>
              {renderDetails()}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
