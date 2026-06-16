import { FormEvent, useEffect, useState } from "react";
import { KeyRound, Loader2, LogIn, Mail, Sparkles, UserPlus } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  fetchDemoAccount,
  forgotPasswordAuth,
  loginAuth,
  registerAuth,
  registerResendAuth,
  registerStartAuth,
  registerVerifyAuth,
  resetPasswordAuth,
  type AuthUser,
} from "@/lib/api";
import { setAuthToken } from "@/lib/auth";
import { isCloudEdition } from "@/lib/edition";

type LoginPageProps = {
  onAuthenticated: (user: AuthUser) => void;
};

type AuthMode =
  | "login"
  | "register"
  | "verify"
  | "forgot"
  | "reset";

export function LoginPage({ onAuthenticated }: LoginPageProps) {
  const [mode, setMode] = useState<AuthMode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [code, setCode] = useState("");
  const [info, setInfo] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [demoEmail, setDemoEmail] = useState<string | null>(null);

  const useEmailVerification = isCloudEdition();

  useEffect(() => {
    void fetchDemoAccount().then((info) => {
      if (info.available && info.email) {
        setDemoEmail(info.email);
      }
    });
  }, []);

  async function handleDemoLogin() {
    if (!demoEmail) return;
    setError(null);
    setInfo(null);
    setLoading(true);
    try {
      const result = await loginAuth(demoEmail, "demo1234");
      setAuthToken(result.access_token);
      onAuthenticated(result.user);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Example account is not ready. Ask the admin to run: python -m personalops_cli admin seed-demo"
      );
    } finally {
      setLoading(false);
    }
  }

  function switchMode(next: AuthMode) {
    setMode(next);
    setError(null);
    setInfo(null);
    if (next !== "verify" && next !== "reset") {
      setCode("");
    }
  }

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setInfo(null);

    const fd = new FormData(e.currentTarget);
    const trimmedEmail = String(fd.get("email") ?? email).trim();
    const passwordValue = String(fd.get("password") ?? password);
    const confirmValue = String(fd.get("confirm") ?? confirm);
    const codeValue = String(fd.get("code") ?? code).trim();

    if (!trimmedEmail) {
      setError("Email is required.");
      return;
    }

    setLoading(true);
    try {
      if (mode === "login") {
        if (!passwordValue) {
          setError("Password is required.");
          return;
        }
        const result = await loginAuth(trimmedEmail, passwordValue);
        setAuthToken(result.access_token);
        onAuthenticated(result.user);
        return;
      }

      if (mode === "register") {
        if (!passwordValue) {
          setError("Password is required.");
          return;
        }
        if (passwordValue.length < 8) {
          setError("Password must be at least 8 characters.");
          return;
        }
        if (passwordValue !== confirmValue) {
          setError("Passwords do not match.");
          return;
        }
        if (useEmailVerification) {
          const res = await registerStartAuth(trimmedEmail, passwordValue);
          setEmail(trimmedEmail);
          setPassword(passwordValue);
          setInfo(res.message);
          switchMode("verify");
          return;
        }
        const result = await registerAuth(trimmedEmail, passwordValue);
        setAuthToken(result.access_token);
        onAuthenticated(result.user);
        return;
      }

      if (mode === "verify") {
        if (!codeValue) {
          setError("Verification code is required.");
          return;
        }
        const result = await registerVerifyAuth(trimmedEmail, codeValue);
        setAuthToken(result.access_token);
        onAuthenticated(result.user);
        return;
      }

      if (mode === "forgot") {
        const res = await forgotPasswordAuth(trimmedEmail);
        setEmail(trimmedEmail);
        setInfo(res.message);
        switchMode("reset");
        return;
      }

      if (mode === "reset") {
        if (!codeValue || !passwordValue) {
          setError("Code and new password are required.");
          return;
        }
        if (passwordValue.length < 8) {
          setError("Password must be at least 8 characters.");
          return;
        }
        if (passwordValue !== confirmValue) {
          setError("Passwords do not match.");
          return;
        }
        const res = await resetPasswordAuth(trimmedEmail, codeValue, passwordValue);
        setInfo(res.message);
        switchMode("login");
        return;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleResendCode() {
    if (!email.trim()) {
      setError("Email is required.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await registerResendAuth(email.trim());
      setInfo(res.message);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not resend code");
    } finally {
      setLoading(false);
    }
  }

  const title =
    mode === "login"
      ? isCloudEdition()
        ? "Cloud edition"
        : "Sign in"
      : mode === "register"
        ? "Create account"
        : mode === "verify"
          ? "Verify email"
          : mode === "forgot"
            ? "Forgot password"
            : "Reset password";

  const subtitle =
    mode === "login"
      ? "Log in to access your workspaces."
      : mode === "register"
        ? "Create an account to get started."
        : mode === "verify"
          ? "Enter the 6-digit code we sent to your email."
          : mode === "forgot"
            ? "We will email you a reset code if the account exists."
            : "Enter the code and choose a new password.";

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-md rounded-3xl border-2 border-zinc-300 bg-card p-8 shadow-md dark:border-zinc-600">
        <div className="mb-6 text-center">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
            PersonalOps
          </p>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight">{title}</h1>
          <p className="mt-2 text-sm text-muted-foreground">{subtitle}</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {(mode === "login" ||
            mode === "register" ||
            mode === "forgot" ||
            mode === "reset" ||
            mode === "verify") && (
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">
                Email
              </label>
              <input
                name="email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                readOnly={mode === "verify"}
                className="w-full rounded-xl border border-zinc-300 bg-background px-3 py-2 text-sm outline-none ring-primary/30 focus:border-zinc-500 focus:ring-2 disabled:opacity-70 dark:border-zinc-600"
                placeholder="you@example.com"
              />
            </div>
          )}

          {(mode === "verify" || mode === "reset") && (
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">
                Verification code
              </label>
              <input
                name="code"
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                className="w-full rounded-xl border border-zinc-300 bg-background px-3 py-2 text-sm tracking-[0.3em] outline-none ring-primary/30 focus:border-zinc-500 focus:ring-2 dark:border-zinc-600"
                placeholder="123456"
                maxLength={6}
              />
            </div>
          )}

          {(mode === "login" || mode === "register" || mode === "reset") && (
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">
                {mode === "reset" ? "New password" : "Password"}
              </label>
              <input
                name="password"
                type="password"
                autoComplete={
                  mode === "login"
                    ? "current-password"
                    : mode === "reset"
                      ? "new-password"
                      : "new-password"
                }
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onInput={(e) => setPassword(e.currentTarget.value)}
                className="w-full rounded-xl border border-zinc-300 bg-background px-3 py-2 text-sm outline-none ring-primary/30 focus:border-zinc-500 focus:ring-2 dark:border-zinc-600"
                placeholder="At least 8 characters"
              />
            </div>
          )}

          {(mode === "register" || mode === "reset") && (
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">
                Confirm password
              </label>
              <input
                name="confirm"
                type="password"
                autoComplete="new-password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                onInput={(e) => setConfirm(e.currentTarget.value)}
                className="w-full rounded-xl border border-zinc-300 bg-background px-3 py-2 text-sm outline-none ring-primary/30 focus:border-zinc-500 focus:ring-2 dark:border-zinc-600"
              />
            </div>
          )}

          {mode === "login" && useEmailVerification && (
            <p className="text-right text-sm">
              <button
                type="button"
                className="font-medium text-primary hover:underline"
                onClick={() => switchMode("forgot")}
              >
                Forgot password?
              </button>
            </p>
          )}

          {info && (
            <p className="rounded-xl border border-primary/20 bg-primary/5 px-3 py-2 text-sm text-foreground">
              {info}
            </p>
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
            ) : mode === "register" ? (
              <UserPlus data-icon="inline-start" className="size-4" />
            ) : mode === "verify" ? (
              <Mail data-icon="inline-start" className="size-4" />
            ) : (
              <KeyRound data-icon="inline-start" className="size-4" />
            )}
            {mode === "login"
              ? "Sign in"
              : mode === "register"
                ? useEmailVerification
                  ? "Send verification code"
                  : "Create account"
                : mode === "verify"
                  ? "Verify and create account"
                  : mode === "forgot"
                    ? "Send reset code"
                    : "Update password"}
          </Button>
        </form>

        {mode === "login" && demoEmail && (
          <div className="mt-4 space-y-2 rounded-xl border border-dashed border-primary/30 bg-primary/5 p-3">
            <p className="text-xs font-medium text-foreground">Try the example account</p>
            <p className="text-xs text-muted-foreground">
              Pre-loaded workspaces (Study, Code, Life, Career) with demo files, chat history,
              inbox, calendar, and study questions. API keys are provided by the platform — you
              cannot add your own on this account.
            </p>
            <Button
              type="button"
              variant="outline"
              className="w-full"
              disabled={loading}
              onClick={() => void handleDemoLogin()}
            >
              <Sparkles data-icon="inline-start" className="size-4" />
              Sign in as {demoEmail}
            </Button>
          </div>
        )}

        {mode === "verify" && (
          <p className="mt-4 text-center text-sm text-muted-foreground">
            Did not get the code?{" "}
            <button
              type="button"
              className="font-medium text-primary hover:underline"
              disabled={loading}
              onClick={() => void handleResendCode()}
            >
              Resend
            </button>
          </p>
        )}

        <p className="mt-4 text-center text-sm text-muted-foreground">
          {mode === "login" && (
            <>
              No account yet?{" "}
              <button
                type="button"
                className="font-medium text-primary hover:underline"
                onClick={() => switchMode("register")}
              >
                Register
              </button>
            </>
          )}
          {mode === "register" && (
            <>
              Already have an account?{" "}
              <button
                type="button"
                className="font-medium text-primary hover:underline"
                onClick={() => switchMode("login")}
              >
                Sign in
              </button>
            </>
          )}
          {(mode === "verify" || mode === "forgot" || mode === "reset") && (
            <>
              Back to{" "}
              <button
                type="button"
                className="font-medium text-primary hover:underline"
                onClick={() => switchMode("login")}
              >
                Sign in
              </button>
            </>
          )}
        </p>
      </div>
    </div>
  );
}
