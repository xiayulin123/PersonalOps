import { FormEvent, useState } from "react";
import { Loader2, LogIn, UserPlus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { loginAuth, registerAuth, type AuthUser } from "@/lib/api";
import { setAuthToken } from "@/lib/auth";
import { isCloudEdition } from "@/lib/edition";

type LoginPageProps = {
  onAuthenticated: (user: AuthUser) => void;
};

export function LoginPage({ onAuthenticated }: LoginPageProps) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    const trimmedEmail = email.trim();
    if (!trimmedEmail || !password) {
      setError("Email and password are required.");
      return;
    }
    if (mode === "register") {
      if (password.length < 8) {
        setError("Password must be at least 8 characters.");
        return;
      }
      if (password !== confirm) {
        setError("Passwords do not match.");
        return;
      }
    }

    setLoading(true);
    try {
      const result =
        mode === "login"
          ? await loginAuth(trimmedEmail, password)
          : await registerAuth(trimmedEmail, password);
      setAuthToken(result.access_token);
      onAuthenticated(result.user);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-md rounded-3xl border-2 border-zinc-300 bg-card p-8 shadow-md dark:border-zinc-600">
        <div className="mb-6 text-center">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
            PersonalOps
          </p>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight">
            {isCloudEdition() ? "Cloud edition" : "Sign in"}
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            {mode === "login"
              ? "Log in to access your workspaces."
              : "Create an account to get started."}
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">
              Email
            </label>
            <input
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-xl border border-zinc-300 bg-background px-3 py-2 text-sm outline-none ring-primary/30 focus:border-zinc-500 focus:ring-2 dark:border-zinc-600"
              placeholder="you@example.com"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">
              Password
            </label>
            <input
              type="password"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-xl border border-zinc-300 bg-background px-3 py-2 text-sm outline-none ring-primary/30 focus:border-zinc-500 focus:ring-2 dark:border-zinc-600"
              placeholder="At least 8 characters"
            />
          </div>
          {mode === "register" && (
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">
                Confirm password
              </label>
              <input
                type="password"
                autoComplete="new-password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                className="w-full rounded-xl border border-zinc-300 bg-background px-3 py-2 text-sm outline-none ring-primary/30 focus:border-zinc-500 focus:ring-2 dark:border-zinc-600"
              />
            </div>
          )}

          {error && (
            <p className="rounded-xl border border-destructive/20 bg-destructive/5 px-3 py-2 text-sm text-destructive">
              {error}
            </p>
          )}

          <Button type="submit" className="w-full" disabled={loading}>
            {loading ? (
              <Loader2 className="size-4 animate-spin" />
            ) : mode === "login" ? (
              <LogIn data-icon="inline-start" className="size-4" />
            ) : (
              <UserPlus data-icon="inline-start" className="size-4" />
            )}
            {mode === "login" ? "Sign in" : "Create account"}
          </Button>
        </form>

        <p className="mt-4 text-center text-sm text-muted-foreground">
          {mode === "login" ? "No account yet?" : "Already have an account?"}{" "}
          <button
            type="button"
            className="font-medium text-primary hover:underline"
            onClick={() => {
              setMode(mode === "login" ? "register" : "login");
              setError(null);
            }}
          >
            {mode === "login" ? "Register" : "Sign in"}
          </button>
        </p>
      </div>
    </div>
  );
}
