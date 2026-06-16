import { useCallback, useEffect, useState } from "react";
import {
  BookMarked,
  ClipboardList,
  Files,
  GraduationCap,
  Loader2,
  Maximize2,
  Minimize2,
  Sparkles,
} from "lucide-react";

import { ConceptCard } from "@/components/ConceptCard";
import { StudyQuestionsPanel } from "@/components/StudyQuestionsPanel";
import { StudyTestsPanel } from "@/components/StudyTestsPanel";
import { Button } from "@/components/ui/button";
import {
  fetchStudySources,
  generateStudyConcepts,
  listStudyConcepts,
  type StudyConcept,
  type StudyLanguage,
  type StudySources,
} from "@/lib/api";
import { cn } from "@/lib/utils";

type StudyTabProps = {
  workspaceId: string;
  onNavigateToFiles?: () => void;
};

type StudyPanel = "concepts" | "questions" | "tests";

const PANEL_META: Record<
  StudyPanel,
  { label: string; description: string; icon: typeof GraduationCap }
> = {
  concepts: {
    label: "Review concepts",
    description: "Flashcard-style concept summaries from your course files.",
    icon: GraduationCap,
  },
  questions: {
    label: "Practice questions",
    description: "Short drills with answers and source citations.",
    icon: ClipboardList,
  },
  tests: {
    label: "Practice tests",
    description: "Timed exams assembled from your uploaded materials.",
    icon: BookMarked,
  },
};

const LANGUAGE_OPTIONS: Array<{ value: StudyLanguage; label: string }> = [
  { value: "english", label: "English" },
  { value: "chinese", label: "Chinese" },
  { value: "bilingual", label: "Bilingual (中文 + EN terms)" },
];

const LANGUAGE_PRESETS: Array<{
  id: string;
  label: string;
  titleLanguage: StudyLanguage;
  contentLanguage: StudyLanguage;
}> = [
  {
    id: "en-zh",
    label: "EN titles · 中文解释",
    titleLanguage: "english",
    contentLanguage: "chinese",
  },
  {
    id: "all-en",
    label: "All English",
    titleLanguage: "english",
    contentLanguage: "english",
  },
  {
    id: "all-zh",
    label: "全中文",
    titleLanguage: "chinese",
    contentLanguage: "chinese",
  },
  {
    id: "bilingual",
    label: "Bilingual",
    titleLanguage: "bilingual",
    contentLanguage: "bilingual",
  },
];

function languageLabel(value: StudyLanguage) {
  return LANGUAGE_OPTIONS.find((option) => option.value === value)?.label ?? value;
}

function LanguageSelect({
  id,
  label,
  value,
  onChange,
}: {
  id: string;
  label: string;
  value: StudyLanguage;
  onChange: (value: StudyLanguage) => void;
}) {
  return (
    <label htmlFor={id} className="space-y-1 text-sm">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <select
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value as StudyLanguage)}
        className="block w-full min-w-[9.5rem] rounded-lg border border-border bg-background px-2 py-1.5 text-sm"
      >
        {LANGUAGE_OPTIONS.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export function StudyTab({ workspaceId, onNavigateToFiles }: StudyTabProps) {
  const [sources, setSources] = useState<StudySources | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedFileIds, setSelectedFileIds] = useState<Set<string>>(new Set());
  const [activePanel, setActivePanel] = useState<StudyPanel>("concepts");

  const [concepts, setConcepts] = useState<StudyConcept[]>([]);
  const [conceptsLoading, setConceptsLoading] = useState(false);
  const [conceptsError, setConceptsError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [conceptCount, setConceptCount] = useState(10);
  const [topicHint, setTopicHint] = useState("");
  const [titleLanguage, setTitleLanguage] = useState<StudyLanguage>("english");
  const [contentLanguage, setContentLanguage] = useState<StudyLanguage>("chinese");
  const [outputsExpanded, setOutputsExpanded] = useState(false);

  const loadSources = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchStudySources(workspaceId);
      setSources(data);
      setSelectedFileIds(new Set(data.files.map((file) => file.id)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load study sources");
      setSources(null);
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  const loadConcepts = useCallback(async () => {
    setConceptsLoading(true);
    setConceptsError(null);
    try {
      const data = await listStudyConcepts(workspaceId);
      setConcepts(data);
    } catch (err) {
      setConceptsError(err instanceof Error ? err.message : "Failed to load concepts");
    } finally {
      setConceptsLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    void loadSources();
  }, [loadSources]);

  useEffect(() => {
    if (activePanel === "concepts") {
      void loadConcepts();
    }
  }, [activePanel, loadConcepts]);

  useEffect(() => {
    if (!outputsExpanded) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOutputsExpanded(false);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [outputsExpanded]);

  function toggleFile(fileId: string) {
    setSelectedFileIds((prev) => {
      const next = new Set(prev);
      if (next.has(fileId)) {
        next.delete(fileId);
      } else {
        next.add(fileId);
      }
      return next;
    });
  }

  function selectAllFiles() {
    if (!sources) return;
    setSelectedFileIds(new Set(sources.files.map((file) => file.id)));
  }

  function deselectAllFiles() {
    setSelectedFileIds(new Set());
  }

  function applyLanguagePreset(
    titleLanguageNext: StudyLanguage,
    contentLanguageNext: StudyLanguage
  ) {
    setTitleLanguage(titleLanguageNext);
    setContentLanguage(contentLanguageNext);
  }

  async function handleGenerateConcepts() {
    if (selectedFileIds.size === 0) return;
    setGenerating(true);
    setConceptsError(null);
    try {
      const result = await generateStudyConcepts(workspaceId, {
        file_ids: Array.from(selectedFileIds),
        count: conceptCount,
        topic_hint: topicHint.trim() || null,
        title_language: titleLanguage,
        content_language: contentLanguage,
      });
      setConcepts((prev) => [...result.concepts, ...prev]);
      if (result.concepts.length > 0) {
        setOutputsExpanded(true);
      }
    } catch (err) {
      setConceptsError(err instanceof Error ? err.message : "Failed to generate concepts");
    } finally {
      setGenerating(false);
    }
  }

  function handleConceptUpdated(updated: StudyConcept) {
    setConcepts((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
  }

  function handleConceptDeleted(conceptId: string) {
    setConcepts((prev) => {
      const next = prev.filter((item) => item.id !== conceptId);
      if (next.length === 0) {
        setOutputsExpanded(false);
      }
      return next;
    });
  }

  function renderConceptList(layout: "default" | "full") {
    return (
      <div className="space-y-3">
        {concepts.map((concept) => (
          <ConceptCard
            key={concept.id}
            workspaceId={workspaceId}
            concept={concept}
            layout={layout}
            onUpdated={handleConceptUpdated}
            onDeleted={handleConceptDeleted}
          />
        ))}
      </div>
    );
  }

  const readyCount = sources?.ready_count ?? 0;
  const hasReadyFiles = readyCount > 0;
  const canGenerate = hasReadyFiles && selectedFileIds.size > 0 && !generating;
  const activePresetId =
    LANGUAGE_PRESETS.find(
      (preset) =>
        preset.titleLanguage === titleLanguage &&
        preset.contentLanguage === contentLanguage
    )?.id ?? null;

  if (loading) {
    return (
      <div className="flex h-full min-h-[320px] items-center justify-center rounded-2xl border-2 border-foreground/15 bg-card">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" />
          Loading study workspace...
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-2xl border-2 border-destructive/20 bg-destructive/5 p-4 text-sm text-destructive">
        <p>{error}</p>
        <Button type="button" size="sm" variant="outline" className="mt-3" onClick={loadSources}>
          Retry
        </Button>
      </div>
    );
  }

  return (
    <>
      <div className="flex h-full min-h-0 flex-col gap-4 overflow-y-auto">
        <section className="shrink-0 rounded-2xl border-2 border-foreground/15 bg-card p-4 shadow-sm">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Course sources
              </p>
              <p className="text-sm text-muted-foreground">
                {hasReadyFiles
                  ? `${readyCount} indexed file${readyCount === 1 ? "" : "s"} ready for generation`
                  : "Upload course PDFs or notes, then wait until status is ready."}
              </p>
            </div>
            {hasReadyFiles && (
              <div className="flex flex-wrap gap-2">
                <Button type="button" size="sm" variant="outline" onClick={selectAllFiles}>
                  Select all
                </Button>
                <Button type="button" size="sm" variant="outline" onClick={deselectAllFiles}>
                  Deselect all
                </Button>
              </div>
            )}
          </div>

          {!hasReadyFiles ? (
            <div className="rounded-xl border border-dashed border-border bg-muted/30 px-4 py-8 text-center">
              <Files className="mx-auto mb-3 size-8 text-muted-foreground" />
              <p className="text-sm font-medium">No indexed course files yet</p>
              <p className="mt-1 text-sm text-muted-foreground">
                Add lecture slides, textbook chapters, or assignment PDFs in the Files tab.
              </p>
              {onNavigateToFiles && (
                <Button
                  type="button"
                  size="sm"
                  className="mt-4"
                  variant="secondary"
                  onClick={onNavigateToFiles}
                >
                  Go to Files
                </Button>
              )}
            </div>
          ) : (
            <ul className="max-h-[min(38vh,280px)] space-y-2 overflow-y-auto pr-1">
              {sources?.files.map((file) => {
                const checked = selectedFileIds.has(file.id);
                return (
                  <li key={file.id}>
                    <label
                      className={cn(
                        "flex cursor-pointer items-center gap-3 rounded-xl border px-3 py-2.5 transition-colors",
                        checked
                          ? "border-primary/30 bg-primary/5"
                          : "border-border hover:bg-muted/40"
                      )}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleFile(file.id)}
                        className="size-4 rounded border-border"
                      />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium">{file.filename}</p>
                        <p className="text-xs text-muted-foreground">
                          {file.chunk_count} chunks · {file.status}
                        </p>
                      </div>
                    </label>
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        <div className="flex shrink-0 flex-wrap gap-2">
          {(Object.keys(PANEL_META) as StudyPanel[]).map((panel) => {
            const meta = PANEL_META[panel];
            const Icon = meta.icon;
            const isActive = activePanel === panel;
            return (
              <button
                key={panel}
                type="button"
                onClick={() => setActivePanel(panel)}
                className={cn(
                  "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm font-medium transition-colors",
                  isActive
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-border bg-card text-muted-foreground hover:text-foreground"
                )}
              >
                <Icon className="size-4" />
                {meta.label}
              </button>
            );
          })}
        </div>

        <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border-2 border-foreground/15 bg-card p-5 shadow-sm">
          <div className="mb-2 flex items-center gap-2">
            <Sparkles className="size-4 text-primary" />
            <h2 className="text-base font-semibold">{PANEL_META[activePanel].label}</h2>
          </div>
          <p className="mb-4 text-sm text-muted-foreground">
            {PANEL_META[activePanel].description}
          </p>

          {activePanel === "concepts" ? (
            <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto">
              <div className="shrink-0 space-y-3 rounded-xl border border-border bg-muted/20 p-3">
                <div className="flex flex-wrap items-end gap-3">
                  <label className="space-y-1 text-sm">
                    <span className="text-xs font-medium text-muted-foreground">Count</span>
                    <input
                      type="number"
                      min={1}
                      max={30}
                      value={conceptCount}
                      onChange={(event) =>
                        setConceptCount(
                          Math.max(1, Math.min(30, Number(event.target.value) || 10))
                        )
                      }
                      className="block w-20 rounded-lg border border-border bg-background px-2 py-1.5"
                    />
                  </label>
                  <LanguageSelect
                    id="concept-title-language"
                    label="Title language"
                    value={titleLanguage}
                    onChange={setTitleLanguage}
                  />
                  <LanguageSelect
                    id="concept-content-language"
                    label="Explanation language"
                    value={contentLanguage}
                    onChange={setContentLanguage}
                  />
                  <label className="min-w-[200px] flex-1 space-y-1 text-sm">
                    <span className="text-xs font-medium text-muted-foreground">
                      Topic hint (optional)
                    </span>
                    <input
                      type="text"
                      value={topicHint}
                      onChange={(event) => setTopicHint(event.target.value)}
                      placeholder="e.g. logistic regression and decision trees"
                      className="block w-full rounded-lg border border-border bg-background px-3 py-1.5"
                    />
                  </label>
                  <Button
                    type="button"
                    disabled={!canGenerate}
                    onClick={() => void handleGenerateConcepts()}
                  >
                    {generating ? (
                      <>
                        <Loader2 className="size-4 animate-spin" />
                        Analyzing {selectedFileIds.size} file
                        {selectedFileIds.size === 1 ? "" : "s"}...
                      </>
                    ) : (
                      "Generate concepts"
                    )}
                  </Button>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs font-medium text-muted-foreground">Quick presets:</span>
                  {LANGUAGE_PRESETS.map((preset) => (
                    <button
                      key={preset.id}
                      type="button"
                      onClick={() =>
                        applyLanguagePreset(preset.titleLanguage, preset.contentLanguage)
                      }
                      className={cn(
                        "rounded-full border px-2.5 py-1 text-xs font-medium transition-colors",
                        activePresetId === preset.id
                          ? "border-primary bg-primary/10 text-primary"
                          : "border-border text-muted-foreground hover:text-foreground"
                      )}
                    >
                      {preset.label}
                    </button>
                  ))}
                </div>
              </div>

              {outputsExpanded && concepts.length > 0 && (
                <div className="flex shrink-0 items-center justify-between gap-2 rounded-xl border border-primary/25 bg-primary/5 px-3 py-2">
                  <p className="text-sm text-foreground">
                    Full-page view is on · {concepts.length} concept
                    {concepts.length === 1 ? "" : "s"}
                  </p>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => setOutputsExpanded(false)}
                  >
                    <Minimize2 className="size-4" />
                    Minimize
                  </Button>
                </div>
              )}

              <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto">
                {concepts.length > 0 && !outputsExpanded && (
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm text-muted-foreground">
                      {concepts.length} concept{concepts.length === 1 ? "" : "s"}
                    </p>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => setOutputsExpanded(true)}
                    >
                      <Maximize2 className="size-4" />
                      Expand full page
                    </Button>
                  </div>
                )}

                {conceptsError && <p className="text-sm text-destructive">{conceptsError}</p>}

                {conceptsLoading ? (
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <Loader2 className="size-4 animate-spin" />
                    Loading concepts...
                  </div>
                ) : concepts.length === 0 ? (
                  <div className="flex flex-1 flex-col items-center justify-center rounded-xl border border-dashed border-border bg-muted/20 px-4 py-10 text-center">
                    <p className="text-sm font-medium">No concepts yet</p>
                    <p className="mt-2 max-w-md text-sm text-muted-foreground">
                      Generate review concepts from your uploaded materials.
                    </p>
                  </div>
                ) : (
                  !outputsExpanded && renderConceptList("default")
                )}
              </div>
            </div>
          ) : activePanel === "questions" ? (
            <StudyQuestionsPanel
              workspaceId={workspaceId}
              selectedFileIds={selectedFileIds}
              canGenerate={canGenerate}
            />
          ) : (
            <StudyTestsPanel
              workspaceId={workspaceId}
              selectedFileIds={selectedFileIds}
              canGenerate={canGenerate}
            />
          )}
        </section>
      </div>

      {outputsExpanded && activePanel === "concepts" && concepts.length > 0 && (
        <div className="fixed inset-0 z-50 flex flex-col bg-background">
          <div className="flex shrink-0 items-center justify-between gap-3 border-b border-border px-4 py-3 md:px-6">
            <div className="min-w-0">
              <p className="text-sm font-semibold">Review concepts — full page</p>
              <p className="truncate text-xs text-muted-foreground">
                {concepts.length} concept{concepts.length === 1 ? "" : "s"} · Title:{" "}
                {languageLabel(titleLanguage)} · Explanation:{" "}
                {languageLabel(contentLanguage)}
              </p>
            </div>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => setOutputsExpanded(false)}
            >
              <Minimize2 className="size-4" />
              Minimize
            </Button>
          </div>
          <div className="flex-1 overflow-y-auto px-4 py-4 md:px-8 md:py-6">
            <div className="mx-auto flex max-w-4xl flex-col gap-5">
              {renderConceptList("full")}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
