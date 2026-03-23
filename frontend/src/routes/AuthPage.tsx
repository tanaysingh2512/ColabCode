import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { forgotPassword, login, register, resetPassword } from "../lib/api";
import { storeAuthSession } from "../lib/auth";
import type { AuthSession } from "../types";

type AuthPageProps = {
  onAuthenticated: (session: AuthSession) => void;
};

type AuthMode = "login" | "register" | "forgot" | "reset";

export function AuthPage({ onAuthenticated }: AuthPageProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const initialResetToken = useMemo(
    () => new URLSearchParams(location.search).get("reset_token") ?? "",
    [location.search],
  );
  const [mode, setMode] = useState<AuthMode>(initialResetToken ? "reset" : "register");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [resetToken, setResetToken] = useState(initialResetToken);
  const [resetUrl, setResetUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const redirectTo = ((location.state as { from?: string } | null)?.from ?? "/");

  useEffect(() => {
    if (initialResetToken) {
      setMode("reset");
      setResetToken(initialResetToken);
    }
  }, [initialResetToken]);

  function switchMode(nextMode: AuthMode) {
    setMode(nextMode);
    setError(null);
    setInfo(null);
    if (nextMode !== "reset") {
      setResetUrl(null);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setInfo(null);
    setIsSubmitting(true);

    try {
      if (mode === "register" || mode === "login") {
        const session =
          mode === "register"
            ? await register({ fullName, email, password })
            : await login({ email, password });
        storeAuthSession(session);
        onAuthenticated(session);
        navigate(redirectTo, { replace: true });
        return;
      }

      if (mode === "forgot") {
        const response = await forgotPassword({ email });
        setInfo(response.message);
        setResetUrl(response.resetUrl);
        if (response.resetToken) {
          setResetToken(response.resetToken);
          setMode("reset");
        }
        return;
      }

      if (password !== confirmPassword) {
        throw new Error("Passwords do not match.");
      }

      const session = await resetPassword({ token: resetToken, newPassword: password });
      storeAuthSession(session);
      onAuthenticated(session);
      navigate(redirectTo, { replace: true });
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Unable to authenticate.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-card panel">
        <p className="eyebrow">CollabCode</p>
        <h1>Collaborative coding like Docs, organized like a project workspace.</h1>
        <p className="hero-copy">
          Sign in to create projects, open shared files, and collaborate in real time with
          live cursors, persistent autosave, and a VS Code-style workspace.
        </p>
        <form className="create-room-form" onSubmit={handleSubmit}>
          {mode === "register" ? (
            <label>
              Full name
              <input
                value={fullName}
                onChange={(event) => setFullName(event.target.value)}
                placeholder="Tanay Singh"
              />
            </label>
          ) : null}
          {mode !== "reset" ? (
            <label>
              Email
              <input
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                type="email"
                placeholder="you@example.com"
              />
            </label>
          ) : null}
          {mode === "reset" ? (
            <label>
              Reset token
              <input
                value={resetToken}
                onChange={(event) => setResetToken(event.target.value)}
                placeholder="Paste the reset token"
              />
            </label>
          ) : null}
          {mode !== "forgot" ? (
            <label>
              {mode === "reset" ? "New password" : "Password"}
              <input
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                type="password"
                placeholder={mode === "reset" ? "Choose a new password" : "Choose a password"}
              />
            </label>
          ) : null}
          {mode === "reset" ? (
            <label>
              Confirm password
              <input
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
                type="password"
                placeholder="Re-enter the new password"
              />
            </label>
          ) : null}
          <button type="submit" disabled={isSubmitting}>
            {isSubmitting
              ? "Working..."
              : mode === "register"
                ? "Create account"
                : mode === "login"
                  ? "Sign in"
                  : mode === "forgot"
                    ? "Send reset link"
                    : "Reset password"}
          </button>
          {info ? <p className="muted">{info}</p> : null}
          {resetUrl ? (
            <p className="muted">
              Demo reset link:{" "}
              <a href={resetUrl} target="_blank" rel="noreferrer">
                open reset flow
              </a>
            </p>
          ) : null}
          {error ? <p className="error-banner">{error}</p> : null}
        </form>
        <div className="auth-actions">
          {mode !== "register" ? (
            <button type="button" className="ghost-button" onClick={() => switchMode("register")}>
              Need an account? Register
            </button>
          ) : null}
          {mode !== "login" ? (
            <button type="button" className="ghost-button" onClick={() => switchMode("login")}>
              Already have an account? Sign in
            </button>
          ) : null}
          {mode !== "forgot" ? (
            <button type="button" className="ghost-button" onClick={() => switchMode("forgot")}>
              Forgot password?
            </button>
          ) : null}
        </div>
      </section>
    </main>
  );
}
