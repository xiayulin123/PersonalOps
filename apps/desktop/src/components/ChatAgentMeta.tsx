import { useEffect, useState } from "react";
import {
  Check,
  Circle,
  ExternalLink,
  FileText,
  Globe,
  Loader2,
  Route,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { submitMessageFeedback, type AgentStep, type ChatSource, type WebSource } from "@/lib/api";
import { cn } from "@/lib/utils";

const SENDING_STEPS = [
  "Classifying request...",
  "Loading workspace memory...",
  "Searching workspace files...",
  "Generating answer...",
] as const;

const ROUTE_LABELS: Record<string, string> = {
  direct: "Direct answer",
  file_rag: "File search",
  web_search: "Web search",
  hybrid: "File + Web",
  local_files: "Local files",
  "local+web": "Local + Web",
  web_only: "Web only",
  insufficient: "Insufficient evidence",
  unknown: "Unknown",
};

function routeBadgeClass(route: string) {
  if (route === "file_rag" || route === "local_files") {
    return "border-primary/30 bg-primary/10 text-primary";
  }
  if (route === "web_search" || route === "web_only") {
    return "border-sky-500/30 bg-sky-500/10 text-sky-700 dark:text-sky-300";
  }
  if (route === "hybrid" || route === "local+web") {
    return "border-violet-500/30 bg-violet-500/10 text-violet-700 dark:text-violet-300";
  }
  if (route === "insufficient") {
    return "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300";
  }
  if (route === "direct") {
    return "border-foreground/20 bg-muted text-muted-foreground";
  }
  return "border-foreground/20 bg-muted text-muted-foreground";
}

function RouteBadge({
  route,
  chatEngine,
}: {
  route?: string;
  chatEngine?: string | null;
}) {
  if (!route) return null;

  const label = ROUTE_LABELS[route] ?? route;

  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      {chatEngine === "cursor_agent" && (
        <span className="inline-flex items-center gap-1 rounded-full border border-violet-500/30 bg-violet-500/10 px-2 py-0.5 text-[0.65rem] font-semibold uppercase tracking-wide text-violet-700 dark:text-violet-300">
          Cursor
        </span>
      )}
      <span
        className={cn(
          "inline-flex items-center gap-1 rounded-full border-2 px-2 py-0.5 text-[0.65rem] font-semibold uppercase tracking-wide",
          routeBadgeClass(route)
        )}
      >
        <Route className="size-3" />
        {label}
      </span>
    </span>
  );
}

export function AgentTraceLive({
  steps,
  route,
  chatEngine,
  running,
}: {
  steps: AgentStep[];
  route?: string;
  chatEngine?: string | null;
  running: boolean;
}) {
  return (
    <details
      open
      className="mt-3 rounded-xl border-2 border-foreground/15 bg-background px-3 py-2 text-xs shadow-sm"
    >
      <summary className="flex cursor-pointer flex-wrap items-center gap-2 font-medium text-muted-foreground">
        {running ? (
          <Loader2 className="size-3.5 animate-spin" />
        ) : (
          <Check className="size-3.5 text-primary" />
        )}
        <span>Agent steps{running ? " · running" : ""}</span>
        <RouteBadge route={route} chatEngine={chatEngine} />
      </summary>
      <ol className="mt-2 space-y-1.5 leading-5">
        {steps.map((step, index) => {
          const isLast = index === steps.length - 1;
          const isActive = running && isLast;

          return (
            <li
              key={`${step.step}-${step.label}-${index}`}
              className={cn(
                "flex items-start gap-2",
                isActive ? "font-medium text-foreground" : "text-muted-foreground"
              )}
            >
              {isActive ? (
                <Loader2 className="mt-0.5 size-3.5 shrink-0 animate-spin text-primary" />
              ) : (
                <Check className="mt-0.5 size-3.5 shrink-0 text-primary" />
              )}
              <span>
                {step.step}. {step.label}
                {step.detail ? (
                  <span className="text-foreground"> → {step.detail}</span>
                ) : null}
              </span>
            </li>
          );
        })}
        {running && steps.length === 0 && (
          <li className="flex items-center gap-2 text-muted-foreground">
            <Loader2 className="size-3.5 shrink-0 animate-spin text-primary" />
            <span>Starting agent...</span>
          </li>
        )}
      </ol>
    </details>
  );
}

export function AgentTracePlaceholder() {
  const [activeStep, setActiveStep] = useState(0);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setActiveStep((current) =>
        current < SENDING_STEPS.length - 1 ? current + 1 : current
      );
    }, 1400);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <details
      open
      className="mt-3 rounded-xl border-2 border-foreground/15 bg-background px-3 py-2 text-xs shadow-sm"
    >
      <summary className="flex cursor-pointer items-center gap-2 font-medium text-muted-foreground">
        <Loader2 className="size-3.5 animate-spin" />
        Agent steps · running
      </summary>
      <ol className="mt-2 space-y-1.5 leading-5">
        {SENDING_STEPS.map((label, index) => {
          const isDone = index < activeStep;
          const isActive = index === activeStep;

          return (
            <li
              key={label}
              className={cn(
                "flex items-center gap-2",
                isDone && "text-foreground",
                isActive && "font-medium text-foreground",
                !isDone && !isActive && "text-muted-foreground/50"
              )}
            >
              {isDone ? (
                <Check className="size-3.5 shrink-0 text-primary" />
              ) : isActive ? (
                <Loader2 className="size-3.5 shrink-0 animate-spin text-primary" />
              ) : (
                <Circle className="size-3 shrink-0" />
              )}
              <span>
                {index + 1}. {label}
              </span>
            </li>
          );
        })}
      </ol>
    </details>
  );
}

export function AgentTrace({
  trace,
  route,
  chatEngine,
}: {
  trace: AgentStep[];
  route?: string;
  chatEngine?: string | null;
}) {
  return (
    <details className="mt-3 rounded-xl border-2 border-foreground/15 bg-background px-3 py-2 text-xs shadow-sm">
      <summary className="flex cursor-pointer flex-wrap items-center gap-2 font-medium text-muted-foreground">
        <span>Agent steps</span>
        <RouteBadge route={route} chatEngine={chatEngine} />
      </summary>
      <ol className="mt-2 space-y-1 leading-5 text-muted-foreground">
        {trace.map((step) => (
          <li key={step.step} className="flex gap-1">
            <span className="shrink-0 font-medium text-foreground">{step.step}.</span>
            <span>
              {step.label}
              {step.detail ? (
                <span className="text-foreground"> → {step.detail}</span>
              ) : null}
            </span>
          </li>
        ))}
      </ol>
    </details>
  );
}

export function FileSourceCard({ source }: { source: ChatSource }) {
  return (
    <div className="rounded-xl border-2 border-foreground/15 bg-background px-3 py-2 text-xs shadow-sm">
      <div className="flex items-center gap-2 font-medium text-foreground">
        <FileText className="size-3.5 shrink-0 text-muted-foreground" />
        <span className="truncate">{source.filename}</span>
        <span className="shrink-0 text-muted-foreground">
          · {source.line != null ? `L.${source.line}` : `p.${source.page}`}
        </span>
      </div>
      <p className="mt-1 line-clamp-3 leading-5 text-muted-foreground">
        {source.snippet}
      </p>
    </div>
  );
}

export function WebSourceCard({ source }: { source: WebSource }) {
  return (
    <div className="rounded-xl border-2 border-sky-500/20 bg-sky-500/3 px-3 py-2 text-xs shadow-sm">
      <div className="flex items-start gap-2">
        <Globe className="mt-0.5 size-3.5 shrink-0 text-sky-600 dark:text-sky-400" />
        <div className="min-w-0 flex-1">
          <a
            href={source.url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 font-medium text-foreground underline-offset-2 hover:underline"
          >
            <span className="truncate">{source.title}</span>
            <ExternalLink className="size-3 shrink-0" />
          </a>
          <p className="mt-0.5 truncate text-[0.65rem] text-muted-foreground">
            {source.url}
          </p>
          <p className="mt-1 line-clamp-3 leading-5 text-muted-foreground">
            {source.snippet}
          </p>
        </div>
      </div>
    </div>
  );
}

export function MessageFeedbackBar({
  messageId,
  initialRating,
  onRated,
}: {
  messageId: string;
  initialRating?: 1 | 5 | null;
  onRated?: (rating: 1 | 5) => void;
}) {
  const [rating, setRating] = useState<1 | 5 | null>(initialRating ?? null);
  const [saving, setSaving] = useState(false);

  async function handleRate(next: 1 | 5) {
    if (saving || rating === next) return;

    setSaving(true);
    try {
      await submitMessageFeedback(messageId, next);
      setRating(next);
      onRated?.(next);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mt-3 flex items-center gap-2 border-t-2 border-foreground/10 pt-3">
      <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
        Feedback
      </span>
      <Button
        type="button"
        size="icon-sm"
        variant={rating === 5 ? "default" : "ghost"}
        disabled={saving}
        onClick={() => handleRate(5)}
        aria-label="Helpful answer"
      >
        {saving && rating !== 5 ? (
          <Loader2 className="size-3.5 animate-spin" />
        ) : (
          <ThumbsUp className="size-3.5" />
        )}
      </Button>
      <Button
        type="button"
        size="icon-sm"
        variant={rating === 1 ? "destructive" : "ghost"}
        disabled={saving}
        onClick={() => handleRate(1)}
        aria-label="Not helpful answer"
      >
        {saving && rating !== 1 ? (
          <Loader2 className="size-3.5 animate-spin" />
        ) : (
          <ThumbsDown className="size-3.5" />
        )}
      </Button>
      {rating && (
        <span className="text-[10px] text-muted-foreground">
          {rating === 5 ? "Marked helpful" : "Marked not helpful"}
        </span>
      )}
    </div>
  );
}

export function AssistantMeta({
  trace,
  route,
  chatEngine,
  sources,
  webSources,
  messageId,
  feedbackRating,
  onFeedback,
}: {
  trace?: AgentStep[];
  route?: string;
  chatEngine?: string | null;
  sources?: ChatSource[];
  webSources?: WebSource[];
  messageId?: string;
  feedbackRating?: 1 | 5 | null;
  onFeedback?: (rating: 1 | 5) => void;
}) {
  const hasFileSources = Boolean(sources?.length);
  const hasWebSources = Boolean(webSources?.length);
  const hasTrace = Boolean(trace?.length);

  if (!hasTrace && !hasFileSources && !hasWebSources && !messageId) {
    return null;
  }

  return (
    <div className={cn("mt-3 space-y-3", (hasTrace || hasFileSources || hasWebSources) && "border-t-2 border-foreground/10 pt-3")}>
      {hasTrace && (
        <AgentTrace trace={trace!} route={route} chatEngine={chatEngine} />
      )}

      {hasFileSources && (
        <details className="rounded-xl border-2 border-foreground/15 bg-background px-3 py-2 text-xs shadow-sm">
          <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            File sources ({sources!.length})
          </summary>
          <div className="mt-2 space-y-2">
            {sources!.map((source, index) => (
              <FileSourceCard
                key={`${source.filename}-${source.page}-${index}`}
                source={source}
              />
            ))}
          </div>
        </details>
      )}

      {hasWebSources && (
        <details className="rounded-xl border-2 border-foreground/15 bg-background px-3 py-2 text-xs shadow-sm">
          <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Web sources ({webSources!.length})
          </summary>
          <div className="mt-2 space-y-2">
            {webSources!.map((source, index) => (
              <WebSourceCard key={`${source.url}-${index}`} source={source} />
            ))}
          </div>
        </details>
      )}

      {messageId && (
        <MessageFeedbackBar
          messageId={messageId}
          initialRating={feedbackRating}
          onRated={onFeedback}
        />
      )}
    </div>
  );
}
