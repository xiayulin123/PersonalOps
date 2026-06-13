import { useCallback, useEffect, useRef, useState } from "react";
import {
  Check,
  CheckCheck,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Loader2,
  Mail,
  RefreshCw,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import type { WorkspaceNavTab } from "@/components/OverviewTab";
import {
  dismissAllInboxBriefs,
  dismissInboxBrief,
  listLifeInbox,
  syncLifePlugins,
  type InboxBrief,
} from "@/lib/api";
import { isLifeEmailConnectUiDisabled, LIFE_EMAIL_CONNECT_CLOUD_NOTE } from "@/lib/edition";
import { cn } from "@/lib/utils";

type LifeInboxTabProps = {
  workspaceId: string;
  refreshKey?: number;
  onNavigate?: (tab: WorkspaceNavTab) => void;
};

function formatRelativeTime(iso: string): string {
  const date = new Date(iso);
  const diffMs = Date.now() - date.getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return date.toLocaleDateString();
}

function providerLabel(provider?: string): string {
  if (provider === "google") return "Gmail";
  return "Outlook";
}

function ProviderChip({
  provider,
  tone = "unread",
}: {
  provider?: string;
  tone?: "unread" | "viewed";
}) {
  return (
    <span
      className={cn(
        "rounded-full border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
        tone === "unread"
          ? "border-sky-500/30 bg-sky-500/10 text-sky-700 dark:text-sky-300"
          : "border-border bg-muted text-muted-foreground"
      )}
    >
      {providerLabel(provider)}
    </span>
  );
}

function useInboxPageSize(): number {
  const [pageSize, setPageSize] = useState(5);

  useEffect(() => {
    const update = () => {
      const height = window.innerHeight;
      if (height < 700) {
        setPageSize(3);
      } else if (height < 900) {
        setPageSize(5);
      } else {
        setPageSize(10);
      }
    };

    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);

  return pageSize;
}

function displaySender(item: InboxBrief): string {
  const name = item.from_name?.trim();
  const address = item.from_address?.trim();
  if (name && name.toLowerCase() !== "unknown") return name;
  if (address && address.toLowerCase() !== "unknown") return address;
  return "Unknown sender";
}

function simplifySummary(text: string): string {
  const lines = text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

  const kept = lines
    .map((line) => line.replace(/^[-*•]\s*/, ""))
    .filter((line) => {
      const normalized = line.replace(/\*\*/g, "").trim();
      return !/^(from|what they want|what:|deadline):/i.test(normalized);
    })
    .map((line) => line.replace(/\*\*/g, "").trim())
    .filter(Boolean);

  if (kept.length > 0) {
    return kept.join(" ");
  }

  return text.replace(/\*\*/g, "").trim() || "No summary available.";
}

function SenderAvatar({
  provider,
  fromName,
  tone = "unread",
}: {
  provider?: string;
  fromName?: string | null;
  tone?: "unread" | "viewed";
}) {
  const letter = (
    fromName?.trim()?.[0] ||
    providerLabel(provider)[0] ||
    "?"
  ).toUpperCase();

  return (
    <div
      className={cn(
        "flex size-10 shrink-0 items-center justify-center rounded-full text-sm font-semibold",
        tone === "unread"
          ? "bg-sky-500/15 text-sky-700 dark:text-sky-300"
          : "bg-muted text-muted-foreground"
      )}
    >
      {letter}
    </div>
  );
}

function InboxBriefCard({
  item,
  onDismiss,
}: {
  item: InboxBrief;
  onDismiss: (id: string) => void;
}) {
  const [showOriginal, setShowOriginal] = useState(false);
  const sender = displaySender(item);
  const summary = simplifySummary(item.summary);

  return (
    <article className="rounded-2xl border border-sky-500/25 bg-sky-50/60 p-4 shadow-sm dark:border-sky-500/20 dark:bg-sky-950/20">
      <div className="flex items-start gap-3">
        <SenderAvatar
          provider={item.provider}
          fromName={item.from_name}
          tone="unread"
        />

        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-1.5">
                <ProviderChip provider={item.provider} tone="unread" />
                <span className="text-[10px] text-sky-700/70 dark:text-sky-300/70">
                  {formatRelativeTime(item.received_at)}
                </span>
              </div>
              <p className="mt-1 line-clamp-2 text-sm font-semibold leading-snug text-sky-950 dark:text-sky-50">
                {item.subject || "(no subject)"}
              </p>
              <p className="mt-0.5 line-clamp-1 text-xs text-sky-800/70 dark:text-sky-200/70">
                {sender}
              </p>
            </div>

            <Button
              type="button"
              size="sm"
              variant="outline"
              className="shrink-0 border-emerald-500/40 bg-emerald-500/10 text-emerald-700 hover:bg-emerald-500/20 dark:text-emerald-300"
              onClick={() => onDismiss(item.id)}
            >
              <Check className="size-4" />
              Done
            </Button>
          </div>

          <div className="mt-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-sky-800/60 dark:text-sky-300/60">
              Summary
            </p>
            <p className="mt-1 text-sm leading-relaxed text-foreground/90">
              {summary}
            </p>
          </div>

          <button
            type="button"
            className="mt-3 flex items-center gap-1 text-xs font-medium text-sky-700 hover:underline dark:text-sky-300"
            onClick={() => setShowOriginal((open) => !open)}
          >
            {showOriginal ? "Hide original email" : "Read original email"}
            <ChevronDown
              className={cn(
                "size-3.5 transition-transform",
                showOriginal && "rotate-180"
              )}
            />
          </button>

          {showOriginal && (
            <div className="mt-2 rounded-lg border border-sky-500/15 bg-white/70 px-3 py-2.5 text-sm leading-relaxed text-foreground/90 whitespace-pre-wrap dark:bg-background/50">
              {item.body_preview?.trim() || "No original content available."}
            </div>
          )}
        </div>
      </div>
    </article>
  );
}

function ViewedMailRow({ item }: { item: InboxBrief }) {
  const [showOriginal, setShowOriginal] = useState(false);

  return (
    <article className="rounded-xl border border-stone-300/50 bg-stone-100/70 px-3 py-2.5 dark:border-stone-600/40 dark:bg-stone-900/30">
      <div className="flex items-start gap-2.5">
        <SenderAvatar
          provider={item.provider}
          fromName={item.from_name}
          tone="viewed"
        />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <ProviderChip provider={item.provider} tone="viewed" />
            <p className="min-w-0 flex-1 truncate text-sm font-medium text-stone-700 dark:text-stone-200">
              {item.subject || "(no subject)"}
            </p>
            <span className="shrink-0 text-xs text-muted-foreground">
              {formatRelativeTime(item.received_at)}
            </span>
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {displaySender(item)}
          </p>
          <p className="mt-1 line-clamp-2 text-sm text-stone-600 dark:text-stone-300">
            {item.body_preview || simplifySummary(item.summary)}
          </p>
          <button
            type="button"
            className="mt-2 flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground"
            onClick={() => setShowOriginal((open) => !open)}
          >
            {showOriginal ? "Hide original" : "Read original"}
            <ChevronDown
              className={cn(
                "size-3.5 transition-transform",
                showOriginal && "rotate-180"
              )}
            />
          </button>
          {showOriginal && (
            <div className="mt-2 rounded-lg border border-stone-300/40 bg-white/50 px-3 py-2 text-sm whitespace-pre-wrap dark:bg-background/40">
              {item.body_preview?.trim() || "No original content available."}
            </div>
          )}
        </div>
      </div>
    </article>
  );
}

function InboxPagination({
  page,
  totalPages,
  totalUnread,
  pageSize,
  loading,
  onPrev,
  onNext,
}: {
  page: number;
  totalPages: number;
  totalUnread: number;
  pageSize: number;
  loading: boolean;
  onPrev: () => void;
  onNext: () => void;
}) {
  if (totalUnread <= pageSize) {
    return null;
  }

  return (
    <div className="flex items-center justify-between gap-2 rounded-xl border border-sky-500/20 bg-sky-50/50 px-3 py-2 dark:border-sky-500/15 dark:bg-sky-950/15">
      <Button
        type="button"
        size="sm"
        variant="outline"
        disabled={loading || page <= 0}
        onClick={onPrev}
        className="gap-1 border-sky-500/30"
      >
        <ChevronLeft className="size-4" />
        Prev
      </Button>
      <p className="text-xs text-muted-foreground">
        Page {page + 1} of {totalPages} · {totalUnread} unread
      </p>
      <Button
        type="button"
        size="sm"
        variant="outline"
        disabled={loading || page >= totalPages - 1}
        onClick={onNext}
        className="gap-1 border-sky-500/30"
      >
        Next
        <ChevronRight className="size-4" />
      </Button>
    </div>
  );
}

export function LifeInboxTab({
  workspaceId,
  refreshKey = 0,
  onNavigate,
}: LifeInboxTabProps) {
  const pageSize = useInboxPageSize();
  const [page, setPage] = useState(0);
  const [briefs, setBriefs] = useState<InboxBrief[]>([]);
  const [viewed, setViewed] = useState<InboxBrief[]>([]);
  const [totalUnread, setTotalUnread] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [readingAll, setReadingAll] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const autoSyncedRef = useRef(false);

  useEffect(() => {
    setPage(0);
  }, [pageSize, workspaceId]);

  const loadInbox = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listLifeInbox(workspaceId, pageSize, page);
      setBriefs(data.items);
      setViewed(data.viewed ?? data.historical ?? []);
      setTotalUnread(data.total_unread ?? data.items.length);
      setTotalPages(data.total_pages ?? 1);
      setConnected(data.connected);
      return data;
    } catch {
      setError("Failed to load inbox.");
      return null;
    } finally {
      setLoading(false);
    }
  }, [workspaceId, pageSize, page]);

  useEffect(() => {
    void loadInbox();
  }, [loadInbox, refreshKey]);

  useEffect(() => {
    autoSyncedRef.current = false;
  }, [workspaceId]);

  useEffect(() => {
    if (!connected || loading || autoSyncedRef.current) return;
    if (briefs.length > 0 || viewed.length > 0 || totalUnread > 0) return;
    autoSyncedRef.current = true;
    void (async () => {
      setSyncing(true);
      try {
        await syncLifePlugins(workspaceId);
        await loadInbox();
      } catch {
        setError("Sync failed. Try Sync manually.");
      } finally {
        setSyncing(false);
      }
    })();
  }, [connected, loading, briefs.length, viewed.length, totalUnread, workspaceId, loadInbox]);

  async function handleSync() {
    setSyncing(true);
    setError(null);
    try {
      await syncLifePlugins(workspaceId);
      await loadInbox();
    } catch {
      setError("Sync failed. Check connection and backend logs.");
    } finally {
      setSyncing(false);
    }
  }

  async function handleDismiss(id: string) {
    const dismissed = briefs.find((item) => item.id === id);
    await dismissInboxBrief(workspaceId, id);
    if (dismissed) {
      setViewed((prev) => [dismissed, ...prev]);
    }
    await loadInbox();
  }

  async function handleReadAll() {
    setReadingAll(true);
    setError(null);
    try {
      await dismissAllInboxBriefs(workspaceId);
      setPage(0);
      await loadInbox();
    } catch {
      setError("Failed to mark all unread as read.");
    } finally {
      setReadingAll(false);
    }
  }

  const isEmpty = briefs.length === 0 && viewed.length === 0 && totalUnread === 0;

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-border bg-card px-4 py-3">
        <div className="flex items-center gap-2">
          <Mail className="size-5 text-primary" />
          <div>
            <p className="text-sm font-semibold">Inbox</p>
            <p className="text-xs text-muted-foreground">
              {connected
                ? `${pageSize} unread per page · ${totalUnread} total unread`
                : isLifeEmailConnectUiDisabled()
                  ? "Email connect available in desktop edition only"
                  : "Connect accounts in Overview to see mail"}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {connected && totalUnread > 0 && (
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={readingAll || loading}
              onClick={() => void handleReadAll()}
              className="border-emerald-500/40 text-emerald-700 hover:bg-emerald-500/10 dark:text-emerald-300"
            >
              {readingAll ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <CheckCheck className="size-4" />
              )}
              Read all
            </Button>
          )}
          {connected && (
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={syncing}
              onClick={() => void handleSync()}
            >
              {syncing ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <RefreshCw className="size-4" />
              )}
              Sync
            </Button>
          )}
        </div>
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
            Loading inbox...
          </div>
        )}

        {!loading && !connected && (
          <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border py-16 text-center">
            <Mail className="mb-3 size-8 text-muted-foreground" />
            <p className="text-sm font-medium">Not connected</p>
            <p className="mt-1 max-w-md text-xs text-muted-foreground">
              {isLifeEmailConnectUiDisabled()
                ? LIFE_EMAIL_CONNECT_CLOUD_NOTE
                : "Connect Microsoft 365 or Google in Overview → Connected Accounts."}
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

        {!loading && connected && isEmpty && !syncing && (
          <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border py-16 text-center">
            <Mail className="mb-3 size-8 text-muted-foreground" />
            <p className="text-sm font-medium">No mail yet</p>
            <p className="mt-1 max-w-sm text-xs text-muted-foreground">
              Tap Sync to pull recent Outlook / Gmail messages.
            </p>
          </div>
        )}

        {!loading && connected && (briefs.length > 0 || totalUnread > 0) && (
          <section className="space-y-3 rounded-2xl border border-sky-500/20 bg-sky-50/30 p-3 dark:border-sky-500/15 dark:bg-sky-950/10">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-sky-800 dark:text-sky-300">
                Unread · AI briefs
              </h3>
              <span className="rounded-full bg-sky-500/15 px-2 py-0.5 text-[10px] font-medium text-sky-800 dark:text-sky-200">
                {totalUnread} unread
              </span>
            </div>

            <InboxPagination
              page={page}
              totalPages={totalPages}
              totalUnread={totalUnread}
              pageSize={pageSize}
              loading={loading}
              onPrev={() => setPage((p) => Math.max(0, p - 1))}
              onNext={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            />

            {briefs.length === 0 ? (
              <p className="py-6 text-center text-sm text-muted-foreground">
                No items on this page.
              </p>
            ) : (
              briefs.map((item) => (
                <InboxBriefCard
                  key={item.id}
                  item={item}
                  onDismiss={(id) => void handleDismiss(id)}
                />
              ))
            )}

            <InboxPagination
              page={page}
              totalPages={totalPages}
              totalUnread={totalUnread}
              pageSize={pageSize}
              loading={loading}
              onPrev={() => setPage((p) => Math.max(0, p - 1))}
              onNext={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            />
          </section>
        )}

        {!loading && connected && viewed.length > 0 && (
          <section className="space-y-2 rounded-2xl border border-stone-300/50 bg-stone-100/40 p-3 dark:border-stone-600/30 dark:bg-stone-900/20">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-stone-600 dark:text-stone-400">
              Viewed
            </h3>
            {viewed.map((item) => (
              <ViewedMailRow key={item.id} item={item} />
            ))}
          </section>
        )}
      </div>
    </div>
  );
}
