import type { AuthSession } from "../types";

const authStorageKey = "collabcode.auth-session";

export function loadAuthSession(): AuthSession | null {
  const raw = sessionStorage.getItem(authStorageKey);
  if (!raw) {
    localStorage.removeItem(authStorageKey);
    return null;
  }

  try {
    return JSON.parse(raw) as AuthSession;
  } catch {
    sessionStorage.removeItem(authStorageKey);
    localStorage.removeItem(authStorageKey);
    return null;
  }
}

export function storeAuthSession(session: AuthSession): void {
  sessionStorage.setItem(authStorageKey, JSON.stringify(session));
  localStorage.removeItem(authStorageKey);
}

export function clearAuthSession(): void {
  sessionStorage.removeItem(authStorageKey);
  localStorage.removeItem(authStorageKey);
}

export function getAccessToken(): string | null {
  return loadAuthSession()?.accessToken ?? null;
}
