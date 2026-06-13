import { useCallback, useEffect, useRef, useState } from "react";
import { isTauri } from "@tauri-apps/api/core";
import { Link2, Loader2, RefreshCw, Unplug, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  completeGoogleOAuth,
  completeOutlookOAuth,
  disconnectGoogle,
  disconnectOutlook,
  getLifeConnections,
  startGoogleOAuth,
  startOutlookOAuth,
  syncLifePlugins,
  type LifeConnectionProvider,
} from "@/lib/api";
import { listenOAuthPopup } from "@/lib/oauth-web";
import {
  isLifeEmailConnectUiDisabled,
  LIFE_EMAIL_CONNECT_CLOUD_NOTE,
  LIFE_EMAIL_CONNECT_CLOUD_TOOLTIP,
} from "@/lib/edition";
import { openExternalUrl } from "@/lib/platform";
import { cn } from "@/lib/utils";

type OAuthCallbackPayload = {
  provider: string;
  code?: string | null;
  state?: string | null;
  error?: string | null;
  error_description?: string | null;
};

type LifeConnectionsCardProps = {
  workspaceId: string;
  refreshKey?: number;
};

const OAUTH_UI_TIMEOUT_MS = 3 * 60 * 1000;

function ProviderRow({
  provider,
  connecting,
  syncing,
  connectDisabled,
  onConnect,
  onDisconnect,
  onSync,
  onCancel,
}: {
  provider: LifeConnectionProvider;
  connecting: boolean;
  syncing: boolean;
  connectDisabled?: boolean;
  onConnect: () => void;
  onDisconnect: () => void;
  onSync: () => void;
  onCancel: () => void;
}) {
  const configHint =
    provider.id === "google"
      ? "Set GOOGLE_CLIENT_ID in API .env"
      : "Set MS_GRAPH_CLIENT_ID in API .env";

  const statusText = connectDisabled
    ? "Unavailable in cloud web - use desktop (Tauri) app"
    : !provider.configured
      ? `API not configured - ${configHint}`
      : provider.connected
        ? `Connected as ${provider.account_email ?? "unknown"}`
        : "Connect once to enable Inbox and Calendar";

  return (
    <div
      title={connectDisabled ? LIFE_EMAIL_CONNECT_CLOUD_TOOLTIP : undefined}
      className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-foreground/10 bg-background px-3 py-3"
    >
      <div className="min-w-0">
        <p className="text-sm font-medium">{provider.label}</p>
        <p className="mt-0.5 text-xs text-muted-foreground">{statusText}</p>
      </div>
      <div className="flex flex-wrap gap-2">
        {provider.connected ? (
          <>
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={syncing}
              onClick={onSync}
            >
              {syncing ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <RefreshCw className="size-4" />
              )}
              Sync
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={connecting}
              onClick={onDisconnect}
            >
              <Unplug className="size-4" />
              Disconnect
            </Button>
          </>
        ) : connecting ? (
          <Button type="button" size="sm" variant="outline" onClick={onCancel}>
            <X className="size-4" />
            Cancel
          </Button>
        ) : (
          <Button
            type="button"
            size="sm"
            disabled={!provider.configured || connectDisabled}
            title={connectDisabled ? LIFE_EMAIL_CONNECT_CLOUD_TOOLTIP : undefined}
            onClick={onConnect}
          >
            Connect {provider.label}
          </Button>
        )}
      </div>
    </div>
  );
}

export function LifeConnectionsCard({
  workspaceId,
  refreshKey = 0,
}: LifeConnectionsCardProps) {
  const [providers, setProviders] = useState<LifeConnectionProvider[]>([]);
  const [loading, setLoading] = useState(true);
  const [connectingId, setConnectingId] = useState<string | null>(null);
  const [connectPhase, setConnectPhase] = useState<"browser" | "completing" | null>(
    null
  );
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const unlistenRef = useRef<(() => void) | null>(null);
  const connectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const connectProviderRef = useRef<"microsoft" | "google" | null>(null);

  const clearConnectSession = useCallback((message?: string) => {
    unlistenRef.current?.();
    unlistenRef.current = null;
    connectProviderRef.current = null;
    if (connectTimeoutRef.current) {
      clearTimeout(connectTimeoutRef.current);
      connectTimeoutRef.current = null;
    }
    if (isTauri()) {
      void import("@tauri-apps/api/core").then(({ invoke }) => {
        void invoke("cancel_oauth_callback_listener").catch(() => {});
      });
    }
    setConnectingId(null);
    setConnectPhase(null);
    if (message) {
      setError(message);
    }
  }, []);

  const loadConnections = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getLifeConnections(workspaceId);
      setProviders(data.providers);
    } catch {
      setError("Failed to load connected accounts.");
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    void loadConnections();
  }, [loadConnections, refreshKey]);

  useEffect(() => {
    return () => {
      clearConnectSession();
    };
  }, [clearConnectSession]);

  const handleOAuthCallback = useCallback(
    async (providerId: "microsoft" | "google", payload: OAuthCallbackPayload) => {
      if (connectTimeoutRef.current) {
        clearTimeout(connectTimeoutRef.current);
        connectTimeoutRef.current = null;
      }

      if (payload.error || !payload.code || !payload.state) {
        clearConnectSession(
          payload.error_description ??
            payload.error ??
            "Sign-in was cancelled or failed."
        );
        return;
      }

      setConnectPhase("completing");

      try {
        if (providerId === "google") {
          await completeGoogleOAuth(workspaceId, {
            code: payload.code,
            state: payload.state,
          });
        } else {
          await completeOutlookOAuth(workspaceId, {
            code: payload.code,
            state: payload.state,
          });
        }
        unlistenRef.current?.();
        unlistenRef.current = null;
        connectProviderRef.current = null;
        setConnectingId(null);
        setConnectPhase(null);
        setError(null);
        await loadConnections();
      } catch (err) {
        clearConnectSession(err instanceof Error ? err.message : "Sign-in failed");
      }
    },
    [workspaceId, loadConnections, clearConnectSession]
  );

  async function handleConnect(providerId: "microsoft" | "google") {
    if (isLifeEmailConnectUiDisabled()) return;

    const provider = providers.find((p) => p.id === providerId);
    if (!provider?.configured) {
      setError(
        providerId === "google"
          ? "Set GOOGLE_CLIENT_ID in personalops/apps/api/.env"
          : "Set MS_GRAPH_CLIENT_ID in personalops/apps/api/.env"
      );
      return;
    }

    clearConnectSession();
    setConnectingId(providerId);
    setConnectPhase("browser");
    connectProviderRef.current = providerId;
    setError(null);

    try {
      if (isTauri()) {
        const { listen } = await import("@tauri-apps/api/event");
        const { invoke } = await import("@tauri-apps/api/core");
        const unlisten = await listen<OAuthCallbackPayload>(
          "oauth-callback",
          (event) => {
            const activeProvider = connectProviderRef.current;
            if (!activeProvider || event.payload.provider !== activeProvider) {
              return;
            }
            void handleOAuthCallback(activeProvider, event.payload);
          }
        );
        unlistenRef.current = unlisten;
        await invoke("start_oauth_callback_listener", { provider: providerId });
      } else {
        unlistenRef.current = listenOAuthPopup(providerId, (payload) => {
          void handleOAuthCallback(providerId, payload);
        });
      }

      connectTimeoutRef.current = setTimeout(() => {
        clearConnectSession(
          "Sign-in timed out. If you closed the browser or saw an error on the login page, click Cancel or try again."
        );
      }, OAUTH_UI_TIMEOUT_MS);

      const start =
        providerId === "google"
          ? await startGoogleOAuth(workspaceId)
          : await startOutlookOAuth(workspaceId);
      await openExternalUrl(start.authorize_url);
    } catch (err) {
      clearConnectSession(err instanceof Error ? err.message : "Failed to start sign-in");
    }
  }

  function handleCancelConnect() {
    clearConnectSession("Sign-in cancelled.");
  }

  async function handleDisconnect(providerId: "microsoft" | "google") {
    setError(null);
    try {
      if (providerId === "google") {
        await disconnectGoogle(workspaceId);
      } else {
        await disconnectOutlook(workspaceId);
      }
      await loadConnections();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to disconnect");
    }
  }

  async function handleSync() {
    setSyncing(true);
    setError(null);
    try {
      await syncLifePlugins(workspaceId);
      await loadConnections();
    } catch {
      setError("Sync failed. Check connection and backend logs.");
    } finally {
      setSyncing(false);
    }
  }

  const anyConnected = providers.some((p) => p.connected);
  const connectingProvider = providers.find((p) => p.id === connectingId);
  const emailConnectDisabled = isLifeEmailConnectUiDisabled();

  return (
    <section className="rounded-2xl border-2 border-foreground/15 bg-card p-4 shadow-sm lg:col-span-2">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Link2 className="size-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold">Connected Accounts</h3>
        </div>
        {anyConnected && (
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={syncing || connectingId !== null}
            onClick={() => void handleSync()}
          >
            {syncing ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <RefreshCw className="size-4" />
            )}
            Sync all
          </Button>
        )}
      </div>

      {emailConnectDisabled && (
        <div className="mb-3 rounded-xl border border-amber-500/30 bg-amber-500/10 px-3 py-2.5 text-xs leading-5 text-amber-900 dark:text-amber-200">
          <p className="font-medium">Email & calendar connect - desktop only</p>
          <p className="mt-1 text-amber-800/90 dark:text-amber-100/90">
            {LIFE_EMAIL_CONNECT_CLOUD_NOTE}
          </p>
        </div>
      )}

      {loading ? (
        <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" />
          Loading connections...
        </div>
      ) : (
        <div className="space-y-3">
          {providers.map((provider) => (
            <ProviderRow
              key={provider.id}
              provider={provider}
              connecting={connectingId === provider.id}
              syncing={syncing}
              connectDisabled={emailConnectDisabled && !provider.connected}
              onConnect={() =>
                void handleConnect(provider.id as "microsoft" | "google")
              }
              onDisconnect={() =>
                void handleDisconnect(provider.id as "microsoft" | "google")
              }
              onSync={() => void handleSync()}
              onCancel={handleCancelConnect}
            />
          ))}

          {connectingId && (
            <div className="flex items-start gap-2 rounded-lg border border-primary/20 bg-primary/5 px-3 py-2 text-xs text-muted-foreground">
              <Loader2 className="mt-0.5 size-3.5 shrink-0 animate-spin" />
              <div>
                {connectPhase === "completing" ? (
                  <>
                    <p>
                      Browser sign-in done. Finishing{" "}
                      {connectingProvider?.label ?? "provider"} connection…
                    </p>
                    <p className="mt-1">
                      Mail and calendar sync run in the background after this
                      step.
                    </p>
                  </>
                ) : (
                  <>
                    <p>
                      Waiting for {connectingProvider?.label ?? "provider"} sign-in
                      in your browser.
                    </p>
                    <p className="mt-1">
                      If login failed or you closed the tab, click{" "}
                      <span className="font-medium text-foreground">Cancel</span> —
                      the spinner will stop within a few minutes at most.
                    </p>
                  </>
                )}
              </div>
            </div>
          )}

          <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
            {providers.map((provider) => (
              <span
                key={provider.id}
                className={cn(
                  "rounded-full border px-2 py-0.5",
                  provider.connected
                    ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                    : "border-border bg-muted"
                )}
              >
                {provider.label} {provider.connected ? "on" : "off"}
              </span>
            ))}
          </div>
        </div>
      )}

      {error && (
        <p className="mt-3 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      )}
    </section>
  );
}
