import { useEffect, useState } from "react";
import { Maximize2, Minimize2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { StudyAttemptResult, StudyQuestion } from "@/lib/api";
import { cn } from "@/lib/utils";

type TestResultsSummaryProps = {
  result: StudyAttemptResult;
  onClose: () => void;
};

function extractFinalFromSteps(steps: string[]): string | null {
  const last = steps[steps.length - 1];
  if (!last) return null;
  const finalMatch = last.match(/final answer:\s*(.+)$/i);
  if (finalMatch) return finalMatch[1].trim();
  if (last.includes("=")) return last.split("=").pop()?.trim() ?? null;
  return last.trim();
}

function parseNumeric(value: string): number | null {
  const cleaned = value.replace(/,/g, "").trim();
  const isPercent = cleaned.includes("%");
  const matches = cleaned.match(/[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?/g);
  if (!matches?.length) return null;
  let num = Number(matches[matches.length - 1]);
  if (!Number.isFinite(num)) return null;
  if (isPercent && num > 1) num /= 100;
  return num;
}

function numericClose(left: string, right: string): boolean {
  const a = parseNumeric(left);
  const b = parseNumeric(right);
  if (a === null || b === null) return left.trim().toLowerCase() === right.trim().toLowerCase();
  const scale = Math.max(Math.abs(a), Math.abs(b), 1e-9);
  return Math.abs(a - b) / scale <= 0.02;
}

function displayCorrectAnswer(question: StudyQuestion): string {
  if (question.question_type !== "calculation" || question.solution_steps.length === 0) {
    return question.correct_answer;
  }
  const stepFinal = extractFinalFromSteps(question.solution_steps);
  if (!stepFinal) return question.correct_answer;
  if (numericClose(question.correct_answer, stepFinal)) return question.correct_answer;
  return stepFinal;
}

type ResultsBodyProps = {
  result: StudyAttemptResult;
  onClose: () => void;
};

function ResultsBody({ result, onClose }: ResultsBodyProps) {
  const score = result.score;
  const autoCorrect = Number(score.auto_scored_correct ?? score.correct ?? 0);
  const autoTotal = Number(score.auto_scored_total ?? 0);
  const totalQuestions = Number(score.total ?? result.questions.length);
  const items = Array.isArray(score.items) ? score.items : [];
  const byTopic =
    score.by_topic && typeof score.by_topic === "object"
      ? (score.by_topic as Record<string, { correct: number; total: number }>)
      : {};

  const questionsById = new Map(result.questions.map((question) => [question.id, question]));

  return (
    <>
      <div className="rounded-xl border border-border bg-muted/20 p-4">
        <p className="text-sm font-semibold">Test results</p>
        <p className="mt-1 text-2xl font-bold">
          {autoCorrect} / {autoTotal} auto-scored correct
        </p>
        <p className="text-sm text-muted-foreground">
          {totalQuestions} total questions · Short answer and calculation are shown for self-review
        </p>
        {Object.keys(byTopic).length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2">
            {Object.entries(byTopic).map(([topic, stats]) => (
              <span
                key={topic}
                className="rounded-full border border-border bg-background px-2.5 py-1 text-xs"
              >
                {topic}: {stats.correct}/{stats.total}
              </span>
            ))}
          </div>
        )}
        <button
          type="button"
          onClick={onClose}
          className="mt-4 text-sm font-medium text-primary hover:underline"
        >
          Back to tests
        </button>
      </div>

      <div className="mx-auto flex w-full max-w-3xl flex-col gap-3 pb-6">
        {items.map((item, index) => {
          const question = questionsById.get(String(item.question_id));
          const autoScored = Boolean(item.auto_scored);
          const isCorrect = item.is_correct;
          const correctAnswer = question ? displayCorrectAnswer(question) : String(item.correct_answer || "—");
          const storedMismatch =
            question &&
            question.question_type === "calculation" &&
            !numericClose(question.correct_answer, correctAnswer);

          return (
            <article
              key={String(item.question_id)}
              className={cn(
                "rounded-xl border p-4",
                autoScored && isCorrect === true && "border-emerald-500/30 bg-emerald-500/5",
                autoScored && isCorrect === false && "border-destructive/30 bg-destructive/5",
                !autoScored && "border-border bg-card"
              )}
            >
              <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
                <span className="font-semibold text-muted-foreground">Q{index + 1}</span>
                {autoScored ? (
                  <span
                    className={cn(
                      "rounded-full px-2 py-0.5 font-medium",
                      isCorrect ? "bg-emerald-500/15 text-emerald-700" : "bg-destructive/15 text-destructive"
                    )}
                  >
                    {isCorrect ? "Correct" : "Incorrect"}
                  </span>
                ) : (
                  <span className="rounded-full bg-muted px-2 py-0.5 font-medium text-muted-foreground">
                    Self-review
                  </span>
                )}
              </div>
              {question && (
                <p className="whitespace-pre-wrap text-sm leading-relaxed">{question.prompt}</p>
              )}
              <div className="mt-3 space-y-1 text-sm">
                <p>
                  <span className="font-medium">Your answer:</span>{" "}
                  {String(item.user_answer || "—")}
                </p>
                <p>
                  <span className="font-medium">Correct answer:</span> {correctAnswer}
                </p>
                {storedMismatch && (
                  <p className="text-xs text-amber-700 dark:text-amber-300">
                    Note: stored answer was adjusted to match the step-by-step solution (
                    {question?.correct_answer}).
                  </p>
                )}
                {question?.explanation && (
                  <p className="text-muted-foreground">{question.explanation}</p>
                )}
                {question?.solution_steps && question.solution_steps.length > 0 && (
                  <ol className="mt-2 list-decimal space-y-1 pl-5 text-muted-foreground">
                    {question.solution_steps.map((step) => (
                      <li key={step}>{step}</li>
                    ))}
                  </ol>
                )}
              </div>
            </article>
          );
        })}
      </div>
    </>
  );
}

export function TestResultsSummary({ result, onClose }: TestResultsSummaryProps) {
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (!expanded) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setExpanded(false);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [expanded]);

  const body = <ResultsBody result={result} onClose={onClose} />;

  return (
    <>
      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto">
        <div className="flex shrink-0 justify-end">
          <Button type="button" size="sm" variant="outline" onClick={() => setExpanded(true)}>
            <Maximize2 className="size-4" />
            Expand full page
          </Button>
        </div>
        {body}
      </div>

      {expanded && (
        <div className="fixed inset-0 z-50 flex flex-col bg-background">
          <div className="flex shrink-0 items-center justify-between gap-3 border-b border-border px-4 py-3 md:px-6">
            <div className="min-w-0">
              <p className="text-sm font-semibold">Test results — full page</p>
              <p className="text-xs text-muted-foreground">
                {result.questions.length} question{result.questions.length === 1 ? "" : "s"}
              </p>
            </div>
            <Button type="button" size="sm" variant="outline" onClick={() => setExpanded(false)}>
              <Minimize2 className="size-4" />
              Minimize
            </Button>
          </div>
          <div className="flex-1 overflow-y-auto px-4 py-4 md:px-8 md:py-6">{body}</div>
        </div>
      )}
    </>
  );
}
