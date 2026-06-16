import { useCallback, useEffect, useState } from "react";
import { Loader2, Maximize2, Minimize2, Trash2 } from "lucide-react";

import { QuestionList } from "@/components/QuestionList";
import {
  DEFAULT_PRACTICE_TYPE_COUNTS,
  hasAnyTypeCount,
  StudyTypeCountInputs,
  totalTypeCounts,
  type StudyQuestionTypeCounts,
} from "@/components/StudyTypeCountInputs";
import { Button } from "@/components/ui/button";
import {
  deleteStudyQuestionSet,
  fetchStudyQuestionSet,
  generateStudyQuestions,
  listStudyQuestionSets,
  type StudyDifficulty,
  type StudyLanguage,
  type StudyQuestionSet,
  type StudyQuestionSetSummary,
} from "@/lib/api";

type StudyQuestionsPanelProps = {
  workspaceId: string;
  selectedFileIds: Set<string>;
  canGenerate: boolean;
};

const DIFFICULTY_OPTIONS: Array<{ value: StudyDifficulty; label: string }> = [
  { value: "easy", label: "Easy" },
  { value: "medium", label: "Medium" },
  { value: "hard", label: "Hard" },
];

const LANGUAGE_OPTIONS: Array<{ value: StudyLanguage; label: string }> = [
  { value: "english", label: "English" },
  { value: "chinese", label: "Chinese" },
  { value: "bilingual", label: "Bilingual" },
];

export function StudyQuestionsPanel({
  workspaceId,
  selectedFileIds,
  canGenerate,
}: StudyQuestionsPanelProps) {
  const [sets, setSets] = useState<StudyQuestionSetSummary[]>([]);
  const [activeSet, setActiveSet] = useState<StudyQuestionSet | null>(null);
  const [activeSetId, setActiveSetId] = useState<string | null>(null);
  const [loadingSets, setLoadingSets] = useState(true);
  const [loadingSet, setLoadingSet] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [partialWarning, setPartialWarning] = useState<string | null>(null);
  const [outputsExpanded, setOutputsExpanded] = useState(false);
  const [revealAllInExpanded, setRevealAllInExpanded] = useState(true);

  const [typeCounts, setTypeCounts] = useState<StudyQuestionTypeCounts>(DEFAULT_PRACTICE_TYPE_COUNTS);
  const [difficulty, setDifficulty] = useState<StudyDifficulty>("medium");
  const [contentLanguage, setContentLanguage] = useState<StudyLanguage>("bilingual");
  const [title, setTitle] = useState("");
  const [topicHint, setTopicHint] = useState("");

  const loadSets = useCallback(async () => {
    setLoadingSets(true);
    setError(null);
    try {
      const data = await listStudyQuestionSets(workspaceId, "practice");
      setSets(data);
      setActiveSetId((current) => current ?? data[0]?.id ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load question sets");
    } finally {
      setLoadingSets(false);
    }
  }, [workspaceId]);

  const loadActiveSet = useCallback(async () => {
    if (!activeSetId) {
      setActiveSet(null);
      return;
    }
    setLoadingSet(true);
    setError(null);
    try {
      const data = await fetchStudyQuestionSet(workspaceId, activeSetId);
      setActiveSet(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load questions");
      setActiveSet(null);
    } finally {
      setLoadingSet(false);
    }
  }, [workspaceId, activeSetId]);

  useEffect(() => {
    void loadSets();
  }, [loadSets]);

  useEffect(() => {
    void loadActiveSet();
  }, [loadActiveSet]);

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

  async function handleGenerate() {
    if (selectedFileIds.size === 0 || !hasAnyTypeCount(typeCounts)) return;
    setGenerating(true);
    setError(null);
    setPartialWarning(null);
    try {
      const result = await generateStudyQuestions(workspaceId, {
        file_ids: Array.from(selectedFileIds),
        type_counts: typeCounts,
        difficulty,
        title: title.trim() || null,
        topic_hint: topicHint.trim() || null,
        content_language: contentLanguage,
      });
      setSets((prev) => {
        const summary: StudyQuestionSetSummary = {
          id: result.question_set.id,
          workspace_id: result.question_set.workspace_id,
          kind: result.question_set.kind,
          title: result.question_set.title,
          question_count: result.question_set.question_count,
          created_at: result.question_set.created_at,
        };
        return [summary, ...prev.filter((item) => item.id !== summary.id)];
      });
      setActiveSetId(result.question_set.id);
      setActiveSet(result.question_set);
      if (result.generated_count < result.requested_count) {
        setPartialWarning(
          `Requested ${result.requested_count} questions but generated ${result.generated_count}. ` +
            "Try a broader topic hint, fewer files, or generate again."
        );
      }
      if (result.question_set.questions.length > 0) {
        setOutputsExpanded(true);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate questions");
    } finally {
      setGenerating(false);
    }
  }

  async function handleDeleteSet() {
    if (!activeSetId || !activeSet) return;
    if (!window.confirm(`Delete "${activeSet.title}"?`)) return;
    setDeleting(true);
    setError(null);
    try {
      await deleteStudyQuestionSet(workspaceId, activeSetId);
      const remaining = sets.filter((item) => item.id !== activeSetId);
      setSets(remaining);
      setActiveSetId(remaining[0]?.id ?? null);
      setActiveSet(null);
      if (remaining.length === 0) {
        setOutputsExpanded(false);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete question set");
    } finally {
      setDeleting(false);
    }
  }

  const generateEnabled = canGenerate && hasAnyTypeCount(typeCounts) && !generating;
  const questionTotal = activeSet?.questions.length ?? 0;

  return (
    <>
      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto">
        <div className="shrink-0 space-y-3 rounded-xl border border-border bg-muted/20 p-3">
          <p className="text-xs font-medium text-muted-foreground">
            Questions per type (0–10 each, at least one type ≥ 1)
          </p>
          <StudyTypeCountInputs
            counts={typeCounts}
            onChange={setTypeCounts}
            disabled={generating}
          />

          <div className="flex flex-wrap items-end gap-3">
            <label className="space-y-1 text-sm">
              <span className="text-xs font-medium text-muted-foreground">Difficulty</span>
              <select
                value={difficulty}
                onChange={(event) => setDifficulty(event.target.value as StudyDifficulty)}
                className="block rounded-lg border border-border bg-background px-2 py-1.5 text-sm"
              >
                {DIFFICULTY_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-xs font-medium text-muted-foreground">Language</span>
              <select
                value={contentLanguage}
                onChange={(event) => setContentLanguage(event.target.value as StudyLanguage)}
                className="block rounded-lg border border-border bg-background px-2 py-1.5 text-sm"
              >
                {LANGUAGE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="min-w-[160px] flex-1 space-y-1 text-sm">
              <span className="text-xs font-medium text-muted-foreground">Set title (optional)</span>
              <input
                type="text"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder="Week 5 practice"
                className="block w-full rounded-lg border border-border bg-background px-3 py-1.5"
              />
            </label>
            <label className="min-w-[180px] flex-1 space-y-1 text-sm">
              <span className="text-xs font-medium text-muted-foreground">Topic hint (optional)</span>
              <input
                type="text"
                value={topicHint}
                onChange={(event) => setTopicHint(event.target.value)}
                placeholder="e.g. SVM and kernel methods"
                className="block w-full rounded-lg border border-border bg-background px-3 py-1.5"
              />
            </label>
            <Button type="button" disabled={!generateEnabled} onClick={() => void handleGenerate()}>
              {generating ? (
                <>
                  <Loader2 className="size-4 animate-spin" />
                  Generating...
                </>
              ) : (
                `Generate questions (${totalTypeCounts(typeCounts)})`
              )}
            </Button>
          </div>
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}
        {partialWarning && (
          <p className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-900 dark:text-amber-200">
            {partialWarning}
          </p>
        )}

        {loadingSets ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
            Loading practice sets...
          </div>
        ) : sets.length === 0 ? (
          <div className="flex flex-1 flex-col items-center justify-center rounded-xl border border-dashed border-border bg-muted/20 px-4 py-10 text-center">
            <p className="text-sm font-medium">No practice questions yet</p>
            <p className="mt-2 max-w-md text-sm text-muted-foreground">
              Generate a question batch from your selected course files.
            </p>
          </div>
        ) : (
          <>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <label className="flex min-w-[200px] flex-1 items-center gap-2 text-sm">
                <span className="shrink-0 text-xs font-medium text-muted-foreground">Practice set</span>
                <select
                  value={activeSetId ?? ""}
                  onChange={(event) => setActiveSetId(event.target.value)}
                  className="w-full rounded-lg border border-border bg-background px-2 py-1.5 text-sm"
                >
                  {sets.map((set) => (
                    <option key={set.id} value={set.id}>
                      {set.title} ({set.question_count})
                    </option>
                  ))}
                </select>
              </label>
              <div className="flex flex-wrap gap-2">
                {questionTotal > 0 && !outputsExpanded && (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => setOutputsExpanded(true)}
                  >
                    <Maximize2 className="size-4" />
                    Expand full page
                  </Button>
                )}
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={!activeSetId || deleting}
                  onClick={() => void handleDeleteSet()}
                >
                  {deleting ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    <Trash2 className="size-4" />
                  )}
                  Delete set
                </Button>
              </div>
            </div>

            {outputsExpanded && questionTotal > 0 && (
              <div className="flex shrink-0 items-center justify-between gap-2 rounded-xl border border-primary/25 bg-primary/5 px-3 py-2">
                <p className="text-sm text-foreground">
                  Full-page view is on · {questionTotal} question{questionTotal === 1 ? "" : "s"}
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

            {loadingSet ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" />
                Loading questions...
              </div>
            ) : activeSet && !outputsExpanded ? (
              <QuestionList questions={activeSet.questions} />
            ) : null}
          </>
        )}
      </div>

      {outputsExpanded && activeSet && activeSet.questions.length > 0 && (
        <div className="fixed inset-0 z-50 flex flex-col bg-background">
          <div className="flex shrink-0 items-center justify-between gap-3 border-b border-border px-4 py-3 md:px-6">
            <div className="min-w-0">
              <p className="text-sm font-semibold">Practice questions — full page</p>
              <p className="truncate text-xs text-muted-foreground">
                {activeSet.title} · {activeSet.questions.length} question
                {activeSet.questions.length === 1 ? "" : "s"}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => setRevealAllInExpanded((prev) => !prev)}
              >
                {revealAllInExpanded ? "Hide all answers" : "Reveal all answers"}
              </Button>
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
          </div>
          <div className="flex-1 overflow-y-auto px-4 py-4 md:px-8 md:py-6">
            <div className="mx-auto max-w-4xl">
              <QuestionList
                questions={activeSet.questions}
                layout="full"
                defaultRevealed={revealAllInExpanded}
              />
            </div>
          </div>
        </div>
      )}
    </>
  );
}
