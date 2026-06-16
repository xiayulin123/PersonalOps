import { useEffect, useMemo, useRef, useState } from "react";
import { Clock, Loader2, Maximize2, Minimize2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { StudyAttemptStart, StudyQuestionTake, StudyQuestionType } from "@/lib/api";
import { cn } from "@/lib/utils";

type PracticeTestRunnerProps = {
  attempt: StudyAttemptStart;
  submitting: boolean;
  onSubmit: (answers: Record<string, string>) => void;
  onCancel: () => void;
};

function questionTypeLabel(type: StudyQuestionType) {
  switch (type) {
    case "mcq":
      return "Multiple choice";
    case "short_answer":
      return "Short answer";
    case "calculation":
      return "Calculation";
    case "true_false":
      return "True / False";
    default:
      return type;
  }
}

function formatTime(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

type TestHeaderProps = {
  attempt: StudyAttemptStart;
  remainingSeconds: number;
  timeLow: boolean;
  submitting: boolean;
  expanded: boolean;
  onCancel: () => void;
  onSubmit: () => void;
  onToggleExpand: () => void;
};

function TestHeader({
  attempt,
  remainingSeconds,
  timeLow,
  submitting,
  expanded,
  onCancel,
  onSubmit,
  onToggleExpand,
}: TestHeaderProps) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3 md:px-6">
      <div className="min-w-0">
        <p className="truncate text-sm font-semibold">
          {attempt.set_title}
          {expanded ? " — full page" : ""}
        </p>
        <p className="text-xs text-muted-foreground">
          {attempt.questions.length} question{attempt.questions.length === 1 ? "" : "s"}
        </p>
      </div>
      <div
        className={cn(
          "flex items-center gap-2 rounded-full border px-3 py-1 text-sm font-medium",
          timeLow
            ? "border-destructive/40 bg-destructive/10 text-destructive"
            : "border-border bg-muted/30"
        )}
      >
        <Clock className="size-4" />
        {formatTime(remainingSeconds)}
      </div>
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" size="sm" onClick={onToggleExpand}>
          {expanded ? (
            <>
              <Minimize2 className="size-4" />
              Minimize
            </>
          ) : (
            <>
              <Maximize2 className="size-4" />
              Expand full page
            </>
          )}
        </Button>
        <Button type="button" variant="outline" size="sm" onClick={onCancel} disabled={submitting}>
          Cancel
        </Button>
        <Button type="button" size="sm" disabled={submitting} onClick={onSubmit}>
          {submitting ? (
            <>
              <Loader2 className="size-4 animate-spin" />
              Submitting...
            </>
          ) : (
            "Submit test"
          )}
        </Button>
      </div>
    </div>
  );
}

type TestQuestionsProps = {
  questions: StudyQuestionTake[];
  answers: Record<string, string>;
  onAnswer: (questionId: string, value: string) => void;
};

function TestQuestions({ questions, answers, onAnswer }: TestQuestionsProps) {
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-4 py-4 pb-6 md:py-6">
      {questions.map((question, index) => (
        <article
          key={question.id}
          className="rounded-2xl border border-border bg-card p-4 shadow-sm"
        >
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <span className="text-xs font-semibold text-muted-foreground">Q{index + 1}</span>
            <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium">
              {questionTypeLabel(question.question_type)}
            </span>
            {question.topic && (
              <span className="text-xs text-muted-foreground">{question.topic}</span>
            )}
          </div>
          <p className="whitespace-pre-wrap text-sm leading-relaxed">{question.prompt}</p>

          <div className="mt-4">
            {question.question_type === "mcq" && question.options ? (
              <div className="space-y-2">
                {question.options.map((option, optionIndex) => {
                  const letter = String.fromCharCode(65 + optionIndex);
                  const selected = answers[question.id] === option;
                  return (
                    <label
                      key={option}
                      className={cn(
                        "flex cursor-pointer items-start gap-2 rounded-lg border px-3 py-2 text-sm",
                        selected ? "border-primary bg-primary/5" : "border-border"
                      )}
                    >
                      <input
                        type="radio"
                        name={`q-${question.id}`}
                        checked={selected}
                        onChange={() => onAnswer(question.id, option)}
                        className="mt-1"
                      />
                      <span>
                        <span className="font-medium">{letter}.</span> {option}
                      </span>
                    </label>
                  );
                })}
              </div>
            ) : question.question_type === "true_false" ? (
              <div className="flex gap-3">
                {["True", "False"].map((option) => (
                  <label
                    key={option}
                    className={cn(
                      "flex cursor-pointer items-center gap-2 rounded-lg border px-4 py-2 text-sm",
                      answers[question.id] === option
                        ? "border-primary bg-primary/5"
                        : "border-border"
                    )}
                  >
                    <input
                      type="radio"
                      name={`q-${question.id}`}
                      checked={answers[question.id] === option}
                      onChange={() => onAnswer(question.id, option)}
                    />
                    {option}
                  </label>
                ))}
              </div>
            ) : (
              <textarea
                value={answers[question.id] ?? ""}
                onChange={(event) => onAnswer(question.id, event.target.value)}
                rows={question.question_type === "calculation" ? 4 : 2}
                placeholder={
                  question.question_type === "calculation"
                    ? "Enter your final answer (with units if needed)"
                    : "Type your answer"
                }
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
              />
            )}
          </div>
        </article>
      ))}
    </div>
  );
}

export function PracticeTestRunner({
  attempt,
  submitting,
  onSubmit,
  onCancel,
}: PracticeTestRunnerProps) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [expanded, setExpanded] = useState(false);
  const totalSeconds = attempt.time_limit_min * 60;
  const startedAt = useMemo(
    () => new Date(attempt.started_at).getTime(),
    [attempt.started_at]
  );
  const [remainingSeconds, setRemainingSeconds] = useState(totalSeconds);
  const autoSubmittedRef = useRef(false);

  useEffect(() => {
    function tick() {
      const elapsed = Math.floor((Date.now() - startedAt) / 1000);
      const next = Math.max(0, totalSeconds - elapsed);
      setRemainingSeconds(next);
    }
    tick();
    const timer = window.setInterval(tick, 1000);
    return () => window.clearInterval(timer);
  }, [startedAt, totalSeconds]);

  useEffect(() => {
    if (remainingSeconds === 0 && !submitting && !autoSubmittedRef.current) {
      autoSubmittedRef.current = true;
      onSubmit(answers);
    }
  }, [remainingSeconds, submitting, answers, onSubmit]);

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

  function setAnswer(questionId: string, value: string) {
    setAnswers((prev) => ({ ...prev, [questionId]: value }));
  }

  const timeLow = remainingSeconds <= 60;
  const header = (
    <TestHeader
      attempt={attempt}
      remainingSeconds={remainingSeconds}
      timeLow={timeLow}
      submitting={submitting}
      expanded={expanded}
      onCancel={onCancel}
      onSubmit={() => onSubmit(answers)}
      onToggleExpand={() => setExpanded((prev) => !prev)}
    />
  );
  const questions = (
    <TestQuestions questions={attempt.questions} answers={answers} onAnswer={setAnswer} />
  );

  return (
    <>
      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto">
        <div className="sticky top-0 z-10 rounded-xl border border-border bg-background/95 backdrop-blur">
          {header}
        </div>
        {questions}
      </div>

      {expanded && (
        <div className="fixed inset-0 z-50 flex flex-col bg-background">
          <div className="shrink-0 bg-background">{header}</div>
          <div className="flex-1 overflow-y-auto px-4 md:px-8">{questions}</div>
        </div>
      )}
    </>
  );
}
