import { useCallback, useEffect, useState } from "react";
import { Calendar, Loader2, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { WorkspaceNavTab } from "@/components/OverviewTab";
import {
  listLifeCalendar,
  syncLifePlugins,
  type LifeCalendarEvent,
} from "@/lib/api";
import { isLifeEmailConnectUiDisabled, LIFE_EMAIL_CONNECT_CLOUD_NOTE } from "@/lib/edition";
import { cn } from "@/lib/utils";

type LifeCalendarTabProps = {
  workspaceId: string;
  refreshKey?: number;
  onNavigate?: (tab: WorkspaceNavTab) => void;
};

function formatEventTime(event: LifeCalendarEvent): string {
  const start = new Date(event.start_at);
  const end = new Date(event.end_at);
  if (event.is_all_day) {
    return "All day";
  }
  const opts: Intl.DateTimeFormatOptions = {
    hour: "numeric",
    minute: "2-digit",
  };
  return `${start.toLocaleTimeString([], opts)} – ${end.toLocaleTimeString([], opts)}`;
}

function groupByDay(events: LifeCalendarEvent[]): Map<string, LifeCalendarEvent[]> {
  const map = new Map<string, LifeCalendarEvent[]>();
  for (const event of events) {
    const key = new Date(event.start_at).toLocaleDateString(undefined, {
      weekday: "long",
      month: "short",
      day: "numeric",
    });
    const list = map.get(key) ?? [];
    list.push(event);
    map.set(key, list);
  }
  return map;
}

export function LifeCalendarTab({
  workspaceId,
  refreshKey = 0,
  onNavigate,
}: LifeCalendarTabProps) {
  const [events, setEvents] = useState<LifeCalendarEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadCalendar = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listLifeCalendar(workspaceId, 7);
      setEvents(data.events);
      setConnected(data.connected);
    } catch {
      setError("Failed to load calendar.");
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    void loadCalendar();
  }, [loadCalendar, refreshKey]);

  async function handleSync() {
    setSyncing(true);
    try {
      await syncLifePlugins(workspaceId);
      await loadCalendar();
    } catch {
      setError("Sync failed.");
    } finally {
      setSyncing(false);
    }
  }

  const grouped = groupByDay(events);

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-border bg-card px-4 py-3">
        <div className="flex items-center gap-2">
          <Calendar className="size-5 text-primary" />
          <div>
            <p className="text-sm font-semibold">Calendar</p>
            <p className="text-xs text-muted-foreground">
              {connected
                ? "Next 7 days from Outlook + Google Calendar"
                : isLifeEmailConnectUiDisabled()
                  ? "Email connect available in desktop edition only"
                  : "Connect accounts in Overview to see events"}
            </p>
          </div>
        </div>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={syncing || !connected}
          onClick={() => void handleSync()}
        >
          {syncing ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <RefreshCw className="size-4" />
          )}
          Refresh
        </Button>
      </div>

      {error && (
        <p className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      )}

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto pb-2">
        {loading && (
          <div className="flex items-center justify-center gap-2 py-16 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
            Loading calendar...
          </div>
        )}

        {!loading && !connected && (
          <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border py-16 text-center">
            <Calendar className="mb-3 size-8 text-muted-foreground" />
            <p className="text-sm font-medium">Not connected</p>
            <p className="mt-1 max-w-md text-xs text-muted-foreground">
              {isLifeEmailConnectUiDisabled()
                ? LIFE_EMAIL_CONNECT_CLOUD_NOTE
                : "Connect Microsoft 365 in Overview → Connected Accounts."}
            </p>
            {onNavigate && !isLifeEmailConnectUiDisabled() && (
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="mt-4"
                onClick={() => onNavigate("overview")}
              >
                Go to Overview
              </Button>
            )}
          </div>
        )}

        {!loading && connected && events.length === 0 && (
          <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border py-16 text-center">
            <Calendar className="mb-3 size-8 text-muted-foreground" />
            <p className="text-sm font-medium">No upcoming events</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Sync from Outlook to see your week here.
            </p>
          </div>
        )}

        {[...grouped.entries()].map(([day, dayEvents]) => (
          <section key={day}>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              {day}
            </h3>
            <ul className="space-y-2">
              {dayEvents.map((event) => (
                <li
                  key={event.id}
                  className={cn(
                    "rounded-xl border border-foreground/10 bg-card px-3 py-2.5"
                  )}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="rounded-full border border-border bg-muted px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                          {event.provider === "google" ? "Google" : "Outlook"}
                        </span>
                        <p className="text-sm font-medium">{event.subject}</p>
                      </div>
                      {event.location && (
                        <p className="mt-0.5 truncate text-xs text-muted-foreground">
                          {event.location}
                        </p>
                      )}
                    </div>
                    <span className="shrink-0 text-xs text-muted-foreground">
                      {formatEventTime(event)}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}
