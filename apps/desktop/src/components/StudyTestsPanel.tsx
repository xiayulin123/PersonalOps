import { useCallback, useEffect, useState } from "react";
import { Loader2, Play, Trash2 } from "lucide-react";

import { PracticeTestRunner } from "@/components/PracticeTestRunner";
import {
  DEFAULT_TEST_TYPE_COUNTS,
  hasAnyTypeCount,
  StudyTypeCountInputs,
  totalTypeCounts,
  type StudyQuestionTypeCounts,
} from "@/components/StudyTypeCountInputs";
import { TestResultsSummary } from "@/components/TestResultsSummary";
import { Button } from "@/components/ui/button";
import {
  deleteStudyQuestionSet,
  fetchStudyQuestionSet,
  generateStudyTest,
  listStudyQuestionSets,
  startStudyTestAttempt,
  submitStudyTestAttempt,
  type StudyAttemptResult,
  type StudyAttemptStart,
  type StudyDifficulty,
  type StudyLanguage,
  type StudyQuestionSet,
  type StudyQuestionSetSummary,
} from "@/lib/api";

type StudyTestsPanelProps = {
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

export function StudyTestsPanel({
  workspaceId,
  selectedFileIds,
  canGenerate,
}: StudyTestsPanelProps) {
  const [sets, setSets] = useState<StudyQuestionSetSummary[]>([]);
  const [activeSet, setActiveSet] = useState<StudyQuestionSet | null>(null);
  const [activeSetId, setActiveSetId] = useState<string | null>(null);
  const [loadingSets, setLoadingSets] = useState(true);
  const [loadingSet, setLoadingSet] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [starting, setStarting] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [partialWarning, setPartialWarning] = useState<string | null>(null);

  const [typeCounts, setTypeCounts] = useState<StudyQuestionTypeCounts>(DEFAULT_TEST_TYPE_COUNTS);
  const [difficulty, setDifficulty] = useState<StudyDifficulty>("medium");
  const [contentLanguage, setContentLanguage] = useState<StudyLanguage>("bilingual");
  const [timeLimitMin, setTimeLimitMin] = useState(45);
  const [title, setTitle] = useState("");
  const [topicHint, setTopicHint] = useState("");

  const [activeAttempt, setActiveAttempt] = useState<StudyAttemptStart | null>(null);
  const [attemptResult, setAttemptResult] = useState<StudyAttemptResult | null>(null);

  const loadSets = useCallback(async () => {
    setLoadingSets(true);
    setError(null);
    try {
      const data = await listStudyQuestionSets(workspaceId, "test");
      setSets(data);
      setActiveSetId((current) => current ?? data[0]?.id ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load tests");
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
      setError(err instanceof Error ? err.message : "Failed to load test");
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

  async function handleGenerate() {
    if (selectedFileIds.size === 0 || !hasAnyTypeCount(typeCounts)) return;
    setGenerating(true);
    setError(null);
    setPartialWarning(null);
    try {
      const result = await generateStudyTest(workspaceId, {
        file_ids: Array.from(selectedFileIds),
        type_counts: typeCounts,
        difficulty,
        title: title.trim() || null,
        topic_hint: topicHint.trim() || null,
        content_language: contentLanguage,
        time_limit_min: timeLimitMin,
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
            "Try a broader topic hint or fewer files."
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate test");
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
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete test");
    } finally {
      setDeleting(false);
    }
  }

  async function handleStartTest() {
    if (!activeSetId) return;
    setStarting(true);
    setError(null);
    setAttemptResult(null);
    try {
      const attempt = await startStudyTestAttempt(workspaceId, activeSetId);
      setActiveAttempt(attempt);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start test");
    } finally {
      setStarting(false);
    }
  }

  async function handleSubmitTest(answers: Record<string, string>) {
    if (!activeAttempt) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = await submitStudyTestAttempt(workspaceId, activeAttempt.attempt_id, answers);
      setAttemptResult(result);
      setActiveAttempt(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to submit test");
    } finally {
      setSubmitting(false);
    }
  }

  const generateEnabled =
    canGenerate && hasAnyTypeCount(typeCounts) && !generating && selectedFileIds.size > 0;
  const timeLimit = Number(activeSet?.settings?.time_limit_min ?? 45);

  if (activeAttempt) {
    return (
      <PracticeTestRunner
        attempt={activeAttempt}
        submitting={submitting}
        onSubmit={(answers) => void handleSubmitTest(answers)}
        onCancel={() => setActiveAttempt(null)}
      />
    );
  }

  if (attemptResult) {
    return (
      <TestResultsSummary result={attemptResult} onClose={() => setAttemptResult(null)} />
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto">
      <div className="shrink-0 space-y-3 rounded-xl border border-border bg-muted/20 p-3">
        <p className="text-xs font-medium text-muted-foreground">
          Questions per type (0–10 each, at least one type ≥ 1)
        </p>
        <StudyTypeCountInputs counts={typeCounts} onChange={setTypeCounts} disabled={generating} />

        <div className="flex flex-wrap items-end gap-3">
          <label className="space-y-1 text-sm">
            <span className="text-xs font-medium text-muted-foreground">Time limit (min)</span>
            <input
              type="number"
              min={5}
              max={180}
              value={timeLimitMin}
              onChange={(event) =>
                setTimeLimitMin(Math.max(5, Math.min(180, Number(event.target.value) || 45)))
              }
              className="block w-24 rounded-lg border border-border bg-background px-2 py-1.5"
            />
          </label>
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
            <span className="text-xs font-medium text-muted-foreground">Test title (optional)</span>
            <input
              type="text"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="Midterm practice"
              className="block w-full rounded-lg border border-border bg-background px-3 py-1.5"
            />
          </label>
          <label className="min-w-[180px] flex-1 space-y-1 text-sm">
            <span className="text-xs font-medium text-muted-foreground">Topic hint (optional)</span>
            <input
              type="text"
              value={topicHint}
              onChange={(event) => setTopicHint(event.target.value)}
              placeholder="e.g. chapters 3–5"
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
              `Generate test (${totalTypeCounts(typeCounts)})`
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
          Loading practice tests...
        </div>
      ) : sets.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center rounded-xl border border-dashed border-border bg-muted/20 px-4 py-10 text-center">
          <p className="text-sm font-medium">No practice tests yet</p>
          <p className="mt-2 max-w-md text-sm text-muted-foreground">
            Generate a timed exam from your selected course files.
          </p>
        </div>
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <label className="flex min-w-[200px] flex-1 items-center gap-2 text-sm">
              <span className="shrink-0 text-xs font-medium text-muted-foreground">Test</span>
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
              <Button
                type="button"
                size="sm"
                disabled={!activeSetId || starting || loadingSet}
                onClick={() => void handleStartTest()}
              >
                {starting ? (
                  <>
                    <Loader2 className="size-4 animate-spin" />
                    Starting...
                  </>
                ) : (
                  <>
                    <Play className="size-4" />
                    Start test
                  </>
                )}
              </Button>
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
                Delete
              </Button>
            </div>
          </div>

          {loadingSet ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" />
              Loading test details...
            </div>
          ) : activeSet ? (
            <div className="rounded-xl border border-border bg-card p-4 text-sm">
              <p className="font-medium">{activeSet.title}</p>
              <p className="mt-1 text-muted-foreground">
                {activeSet.question_count} questions · {timeLimit} min limit ·{" "}
                {String(activeSet.settings?.difficulty ?? "medium")} difficulty
              </p>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}
