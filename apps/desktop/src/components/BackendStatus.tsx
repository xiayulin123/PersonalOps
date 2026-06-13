import { useCallback, useEffect, useState } from "react";
import { Loader2, RefreshCw, Wifi, WifiOff } from "lucide-react";

import { Button } from "@/components/ui/button";
import { checkHealth, fetchStorageStatus, type HealthStatus, type StorageStatus } from "@/lib/api";
import { isCloudEdition } from "@/lib/edition";
import { cn } from "@/lib/utils";

type BackendStatusProps = {
  refreshKey?: number;
  onRefresh?: () => void;
};

export function BackendStatus({ refreshKey = 0, onRefresh }: BackendStatusProps) {
  const [status, setStatus] = useState<"loading" | "ok" | "error">("loading");
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [storage, setStorage] = useState<StorageStatus | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const runCheck = useCallback(async () => {
    setRefreshing(true);
    setStatus("loading");
    try {
      const payload = await checkHealth();
      setHealth(payload);
      if (isCloudEdition()) {
        try {
          const storageStatus = await fetchStorageStatus();
          setStorage(storageStatus);
        } catch {
          setStorage(null);
        }
      } else {
        setStorage(null);
      }
      setStatus("ok");
    } catch {
      setHealth(null);
      setStorage(null);
      setStatus("error");
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    runCheck();
  }, [runCheck, refreshKey]);

  function handleRefresh() {
    onRefresh?.();
    if (!onRefresh) {
      void runCheck();
    }
  }

  const label =
    status === "loading"
      ? "Connecting"
      : status === "ok"
        ? health?.status === "degraded"
          ? "Backend degraded"
          : "Backend online"
        : "Backend offline";

  const healthHint = health
    ? [
        `OpenAI: ${health.openai_configured ? "on" : "off"}`,
        `Cursor: ${health.cursor_configured ? "on" : "off"}`,
        `Chroma: ${health.chroma_ok ? "ok" : "down"}`,
        `Web: ${health.web_provider}`,
        `OCR: ${health.ocr_available ? health.ocr_provider : "off"}`,
        storage
          ? `GCS: ${storage.connection_ok ? "connected" : storage.detail} · exports: ${storage.conversation_exports_count}`
          : null,
      ]
        .filter(Boolean)
        .join(" · ")
    : undefined;

  return (
    <div className="flex items-center gap-2">
      {isCloudEdition() && storage && (
        <div
          title={storage.detail}
          className={cn(
            "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium",
            storage.connection_ok
              ? "border-sky-500/20 bg-sky-500/10 text-sky-700 dark:text-sky-300"
              : "border-destructive/20 bg-destructive/10 text-destructive"
          )}
        >
          {storage.connection_ok ? "GCS connected" : "GCS error"}
        </div>
      )}
      <div
        title={healthHint}
        className={cn(
          "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium",
          status === "ok" &&
            health?.status !== "degraded" &&
            "border-emerald-500/20 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
          status === "ok" &&
            health?.status === "degraded" &&
            "border-amber-500/25 bg-amber-500/10 text-amber-800 dark:text-amber-300",
          status === "error" &&
            "border-destructive/20 bg-destructive/10 text-destructive",
          status === "loading" &&
            "border-border bg-muted text-muted-foreground"
        )}
      >
        {(status === "loading" || refreshing) && (
          <Loader2 className="size-3.5 animate-spin" />
        )}
        {status === "ok" && !refreshing && <Wifi className="size-3.5" />}
        {status === "error" && !refreshing && <WifiOff className="size-3.5" />}
        {label}
      </div>
      <Button
        type="button"
        size="icon-sm"
        variant="outline"
        onClick={handleRefresh}
        disabled={refreshing}
        title="Refresh backend connection and reload workspaces"
        aria-label="Refresh"
      >
        <RefreshCw className={cn("size-3.5", refreshing && "animate-spin")} />
      </Button>
    </div>
  );
}
