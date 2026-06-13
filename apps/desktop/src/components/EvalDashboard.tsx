import { useCallback, useEffect, useState } from "react";
import { BarChart3, Clock3, Loader2, MessageSquareQuote, ThumbsDown, ThumbsUp } from "lucide-react";

import { Button } from "@/components/ui/button";
import { getMetricsSummary, type MetricsSummary } from "@/lib/api";
import { cn } from "@/lib/utils";

type EvalDashboardProps = {
  workspaceId: string;
  refreshKey?: number;
};

const ROUTE_LABELS: Record<string, string> = {
  file_rag: "File RAG",
  web_search: "Web search",
  hybrid: "Hybrid",
  direct: "Direct",
};

const ROUTE_COLORS: Record<string, string> = {
  file_rag: "bg-emerald-500",
  web_search: "bg-sky-500",
  hybrid: "bg-violet-500",
  direct: "bg-amber-500",
};

function MetricCard({
  label,
  value,
  hint,
  icon: Icon,
}: {
  label: string;
  value: string;
  hint?: string;
  icon: typeof BarChart3;
}) {
  return (
    <div className="rounded-2xl border-2 border-foreground/15 bg-card p-4 shadow-sm">
      <div className="flex items-center gap-2 text-muted-foreground">
        <Icon className="size-4" />
        <span className="text-xs font-semibold uppercase tracking-wide">{label}</span>
      </div>
      <p className="mt-2 text-2xl font-semibold tracking-tight">{value}</p>
      {hint && <p className="mt-1 text-xs leading-5 text-muted-foreground">{hint}</p>}
    </div>
  );
}

function RouteBreakdownChart({ breakdown }: { breakdown: Record<string, number> }) {
  const entries = Object.entries(breakdown).sort((a, b) => b[1] - a[1]);
  const max = Math.max(...entries.map(([, count]) => count), 1);

  if (entries.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No routed chats recorded yet. Send a few messages in Chat.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {entries.map(([route, count]) => (
        <div key={route}>
          <div className="mb-1 flex items-center justify-between text-xs">
            <span className="font-medium text-foreground">
              {ROUTE_LABELS[route] ?? route}
            </span>
            <span className="text-muted-foreground">{count}</span>
          </div>
          <div className="h-2 rounded-full bg-muted">
            <div
              className={cn(
                "h-2 rounded-full transition-all",
                ROUTE_COLORS[route] ?? "bg-primary"
              )}
              style={{ width: `${Math.max(8, (count / max) * 100)}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

export function EvalDashboard({ workspaceId, refreshKey = 0 }: EvalDashboardProps) {
  const [summary, setSummary] = useState<MetricsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadSummary = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getMetricsSummary(workspaceId);
      setSummary(data);
      setError(null);
    } catch {
      setError("Failed to load evaluation metrics");
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    void loadSummary();
  }, [loadSummary, refreshKey]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 rounded-2xl border-2 border-foreground/15 bg-card px-4 py-8 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" />
        Loading evaluation metrics...
      </div>
    );
  }

  if (error || !summary) {
    return (
      <div className="rounded-2xl border-2 border-destructive/20 bg-destructive/5 px-4 py-6 text-sm text-destructive">
        {error ?? "Metrics unavailable"}
      </div>
    );
  }

  const citationPct = Math.round(summary.citation_rate * 100);
  const feedbackTotal = summary.feedback_up + summary.feedback_down;

  return (
    <div className="flex h-full min-h-0 flex-col gap-6 overflow-y-auto">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <BarChart3 className="size-4 text-muted-foreground" />
            <h3 className="text-sm font-semibold">Evaluation dashboard</h3>
          </div>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            Aggregated chat latency, citation coverage, route mix, and thumbs feedback
            for this workspace.
          </p>
        </div>
        <Button type="button" size="sm" variant="outline" onClick={loadSummary}>
          Refresh
        </Button>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Total chats"
          value={String(summary.total_chats)}
          hint="Completed agent runs recorded"
          icon={MessageSquareQuote}
        />
        <MetricCard
          label="Avg latency"
          value={`${summary.avg_latency_ms} ms`}
          hint="End-to-end agent response time"
          icon={Clock3}
        />
        <MetricCard
          label="Citation rate"
          value={`${citationPct}%`}
          hint="Chats with at least one file source"
          icon={BarChart3}
        />
        <MetricCard
          label="Feedback"
          value={feedbackTotal ? `${summary.feedback_up}↑ / ${summary.feedback_down}↓` : "—"}
          hint="Thumbs on assistant messages"
          icon={ThumbsUp}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-2xl border-2 border-foreground/15 bg-card p-4 shadow-sm">
          <h4 className="text-sm font-semibold">Route breakdown</h4>
          <p className="mt-1 text-xs text-muted-foreground">
            How often each routing path was chosen.
          </p>
          <div className="mt-4">
            <RouteBreakdownChart breakdown={summary.route_breakdown} />
          </div>
        </div>

        <div className="rounded-2xl border-2 border-foreground/15 bg-card p-4 shadow-sm">
          <h4 className="text-sm font-semibold">Feedback quality</h4>
          <p className="mt-1 text-xs text-muted-foreground">
            Use thumbs up/down under assistant replies in Chat.
          </p>
          <div className="mt-4 space-y-3">
            <div className="flex items-center justify-between rounded-xl border border-foreground/10 bg-muted/20 px-3 py-2 text-sm">
              <span className="inline-flex items-center gap-2">
                <ThumbsUp className="size-4 text-emerald-600" />
                Helpful
              </span>
              <span className="font-semibold">{summary.feedback_up}</span>
            </div>
            <div className="flex items-center justify-between rounded-xl border border-foreground/10 bg-muted/20 px-3 py-2 text-sm">
              <span className="inline-flex items-center gap-2">
                <ThumbsDown className="size-4 text-destructive" />
                Not helpful
              </span>
              <span className="font-semibold">{summary.feedback_down}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
