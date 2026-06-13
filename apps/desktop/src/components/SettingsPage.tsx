import { useCallback, useEffect, useState } from "react";
import { KeyRound, Loader2, Save } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  fetchUserCredentials,
  upsertUserCredential,
  type UserCredential,
} from "@/lib/api";

type SettingsPageProps = {
  onClose?: () => void;
};

const PROVIDER_META: Record<
  UserCredential["provider"],
  { label: string; placeholder: string; help: string; required?: boolean }
> = {
  openai: {
    label: "OpenAI API key",
    placeholder: "sk-...",
    help: "Required for chat and file indexing (embeddings) in cloud mode.",
    required: true,
  },
  tavily: {
    label: "Tavily API key",
    placeholder: "tvly-...",
    help: "Optional. Enables web search when Tools → Web search is on.",
  },
};

export function SettingsPage({ onClose }: SettingsPageProps) {
  const [items, setItems] = useState<UserCredential[]>([]);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<UserCredential["provider"] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchUserCredentials();
      setItems(data.items);
      setDrafts({});
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load API keys");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleSave(provider: UserCredential["provider"]) {
    setSaving(provider);
    setError(null);
    setMessage(null);
    try {
      const updated = await upsertUserCredential(provider, drafts[provider] ?? "");
      setItems((prev) =>
        prev.map((item) => (item.provider === provider ? updated : item))
      );
      setDrafts((prev) => ({ ...prev, [provider]: "" }));
      setMessage(
        updated.configured
          ? `${PROVIDER_META[provider].label} saved.`
          : `${PROVIDER_META[provider].label} removed.`
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save API key");
    } finally {
      setSaving(null);
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-6 overflow-y-auto rounded-2xl border-2 border-foreground/15 bg-card p-4 shadow-sm">
      <div className="flex shrink-0 items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <KeyRound className="size-4 text-muted-foreground" />
            <h2 className="text-sm font-semibold">Account Settings</h2>
          </div>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            Your API keys are encrypted in the database and used only for your
            account. They are never shown in full after saving.
          </p>
        </div>
        {onClose && (
          <Button type="button" size="sm" variant="ghost" onClick={onClose}>
            Close
          </Button>
        )}
      </div>

      {loading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" />
          Loading API keys...
        </div>
      ) : (
        <div className="space-y-4">
          {items.map((item) => {
            const meta = PROVIDER_META[item.provider];
            return (
              <div
                key={item.provider}
                className="rounded-2xl border-2 border-foreground/15 bg-background p-4 shadow-sm"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-sm font-semibold">{meta.label}</p>
                  {meta.required && (
                    <span className="rounded-full border border-primary/25 bg-primary/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-primary">
                      Required
                    </span>
                  )}
                  {item.configured && (
                    <span className="text-xs text-muted-foreground">
                      Current: {item.masked}
                    </span>
                  )}
                </div>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">{meta.help}</p>
                <input
                  type="password"
                  autoComplete="off"
                  placeholder={
                    item.configured
                      ? "Enter new key to replace, or leave empty and Save to remove"
                      : meta.placeholder
                  }
                  value={drafts[item.provider] ?? ""}
                  onChange={(event) =>
                    setDrafts((prev) => ({
                      ...prev,
                      [item.provider]: event.target.value,
                    }))
                  }
                  className="mt-3 w-full rounded-xl border border-border bg-background px-3 py-2 text-sm outline-none ring-primary/30 focus:border-primary/40 focus:ring-2"
                />
                <div className="mt-3">
                  <Button
                    type="button"
                    size="sm"
                    disabled={saving === item.provider}
                    onClick={() => void handleSave(item.provider)}
                  >
                    {saving === item.provider ? (
                      <Loader2 className="size-4 animate-spin" />
                    ) : (
                      <Save className="size-4" />
                    )}
                    Save
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {error && (
        <div className="rounded-xl border border-destructive/20 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}
      {message && (
        <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 px-3 py-2 text-sm text-emerald-800 dark:text-emerald-300">
          {message}
        </div>
      )}
    </div>
  );
}
