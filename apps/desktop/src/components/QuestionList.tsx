import { useEffect, useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { StudyQuestion } from "@/lib/api";
import { cn } from "@/lib/utils";

type QuestionListProps = {
  questions: StudyQuestion[];
  layout?: "default" | "full";
  defaultRevealed?: boolean;
};

function questionTypeLabel(type: StudyQuestion["question_type"]) {
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

function QuestionItem({
  question,
  index,
  layout,
  defaultRevealed,
}: {
  question: StudyQuestion;
  index: number;
  layout: "default" | "full";
  defaultRevealed: boolean;
}) {
  const [revealed, setRevealed] = useState(defaultRevealed);
  const isFull = layout === "full";

  useEffect(() => {
    setRevealed(defaultRevealed);
  }, [defaultRevealed, question.id]);

  return (
    <article
      className={cn(
        "rounded-2xl border-2 border-foreground/10 bg-card shadow-sm",
        isFull ? "p-5 md:p-6" : "p-4"
      )}
    >
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <span className="rounded-full border border-border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
              Q{index + 1}
            </span>
            <span className="rounded-full border border-primary/20 bg-primary/5 px-2 py-0.5 text-[11px] font-medium text-primary">
              {questionTypeLabel(question.question_type)}
            </span>
            {question.topic && (
              <span className="text-xs text-muted-foreground">{question.topic}</span>
            )}
          </div>
          <p
            className={cn(
              "font-medium leading-relaxed",
              isFull ? "text-base md:text-lg" : "text-sm md:text-base"
            )}
          >
            {question.prompt}
          </p>
        </div>
        {!defaultRevealed && (
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => setRevealed((prev) => !prev)}
          >
            {revealed ? (
              <>
                <ChevronUp className="size-4" />
                Hide answer
              </>
            ) : (
              <>
                <ChevronDown className="size-4" />
                Reveal answer
              </>
            )}
          </Button>
        )}
      </div>

      {question.options && question.options.length > 0 && (
        <ul className="mb-3 space-y-2">
          {question.options.map((option, optionIndex) => (
            <li
              key={`${question.id}-option-${optionIndex}`}
              className={cn(
                "rounded-xl border px-3 py-2 text-sm",
                revealed && option === question.correct_answer
                  ? "border-emerald-500/35 bg-emerald-500/10 font-medium"
                  : "border-border bg-muted/20",
                isFull && "text-base"
              )}
            >
              {option}
            </li>
          ))}
        </ul>
      )}

      {revealed && (
        <div className="space-y-3 rounded-xl border border-emerald-500/25 bg-emerald-500/5 p-3">
          {question.question_type === "calculation" && question.solution_steps.length > 0 && (
            <div>
              <p className="mb-2 text-sm font-semibold text-foreground">Solution steps</p>
              <ol
                className={cn(
                  "list-decimal space-y-2 pl-5 leading-relaxed",
                  isFull ? "text-base" : "text-sm"
                )}
              >
                {question.solution_steps.map((step, stepIndex) => (
                  <li key={`${question.id}-step-${stepIndex}`}>{step}</li>
                ))}
              </ol>
            </div>
          )}
          <p className={cn(isFull ? "text-base" : "text-sm")}>
            <span className="font-semibold text-emerald-800 dark:text-emerald-200">
              {question.question_type === "calculation" ? "Final answer: " : "Answer: "}
            </span>
            {question.correct_answer}
          </p>
          {question.explanation && (
            <p className={cn("text-muted-foreground", isFull ? "text-base" : "text-sm")}>
              <span className="font-medium text-foreground">
                {question.question_type === "calculation" ? "Notes: " : "Explanation: "}
              </span>
              {question.explanation}
            </p>
          )}
          {question.sources.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {question.sources.map((source, sourceIndex) => (
                <span
                  key={`${question.id}-source-${sourceIndex}`}
                  className="rounded-full border border-border px-2 py-0.5 text-[11px] text-muted-foreground"
                >
                  {source.filename}
                  {source.page > 0 ? ` · p.${source.page}` : ""}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </article>
  );
}

export function QuestionList({
  questions,
  layout = "default",
  defaultRevealed = false,
}: QuestionListProps) {
  if (questions.length === 0) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center rounded-xl border border-dashed border-border bg-muted/20 px-4 py-10 text-center">
        <p className="text-sm font-medium">No questions in this set</p>
      </div>
    );
  }

  return (
    <div className={cn("space-y-3", layout === "full" && "space-y-5")}>
      {questions.map((question, index) => (
        <QuestionItem
          key={question.id}
          question={question}
          index={index}
          layout={layout}
          defaultRevealed={defaultRevealed}
        />
      ))}
    </div>
  );
}
