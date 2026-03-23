import { getAccessToken } from "./auth";
import type {
  AuthSession,
  AuthUser,
  CollaborationSession,
  ExecutionResult,
  FileRecord,
  Language,
  ProjectDetail,
  ProjectSummary,
  ShareMode,
} from "../types";

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1").replace(
  /\/$/,
  "",
);
const wsBaseUrl =
  import.meta.env.VITE_WS_BASE_URL ??
  `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.hostname}:8000/ws`;

type AuthApiPayload = {
  access_token: string;
  token_type: string;
  user: {
    id: string;
    email: string;
    full_name: string;
    created_at: string;
  };
};

type ProjectSummaryApiPayload = {
  id: string;
  name: string;
  owner_id: string;
  share_mode: ShareMode;
  file_count: number;
  default_file_id: string | null;
  created_at: string;
  updated_at: string;
};

type FileApiPayload = {
  id: string;
  project_id: string;
  name: string;
  language: Language;
  latest_state_size: number;
  created_at: string;
  updated_at: string;
  share_url: string;
};

type ProjectDetailApiPayload = {
  id: string;
  name: string;
  owner_id: string;
  share_mode: ShareMode;
  created_at: string;
  updated_at: string;
  files: FileApiPayload[];
};

type FileJoinApiPayload = {
  project_id: string;
  file_id: string;
  share_mode: ShareMode;
};

type ForgotPasswordApiPayload = {
  message: string;
  reset_token: string | null;
  reset_url: string | null;
};

type ValidationErrorPayload = {
  type: string;
  loc: Array<string | number>;
  msg: string;
  ctx?: {
    min_length?: number;
    max_length?: number;
  };
};

function normalizeUser(payload: AuthApiPayload["user"]): AuthUser {
  return {
    id: payload.id,
    email: payload.email,
    fullName: payload.full_name,
    createdAt: payload.created_at,
  };
}

function normalizeAuth(payload: AuthApiPayload): AuthSession {
  return {
    accessToken: payload.access_token,
    tokenType: payload.token_type,
    user: normalizeUser(payload.user),
  };
}

function normalizeProjectSummary(payload: ProjectSummaryApiPayload): ProjectSummary {
  return {
    id: payload.id,
    name: payload.name,
    ownerId: payload.owner_id,
    shareMode: payload.share_mode,
    fileCount: payload.file_count,
    defaultFileId: payload.default_file_id,
    createdAt: payload.created_at,
    updatedAt: payload.updated_at,
  };
}

function normalizeFile(payload: FileApiPayload): FileRecord {
  return {
    id: payload.id,
    projectId: payload.project_id,
    name: payload.name,
    language: payload.language,
    latestStateSize: payload.latest_state_size,
    createdAt: payload.created_at,
    updatedAt: payload.updated_at,
    shareUrl: payload.share_url,
  };
}

function normalizeProjectDetail(payload: ProjectDetailApiPayload): ProjectDetail {
  return {
    id: payload.id,
    name: payload.name,
    ownerId: payload.owner_id,
    shareMode: payload.share_mode,
    createdAt: payload.created_at,
    updatedAt: payload.updated_at,
    files: payload.files.map(normalizeFile),
  };
}

function formatValidationMessage(detail: ValidationErrorPayload[]): string | null {
  if (!Array.isArray(detail) || detail.length === 0) {
    return null;
  }

  const firstError = detail[0];
  const field = firstError.loc[firstError.loc.length - 1];
  if ((field === "password" || field === "new_password") && firstError.type === "string_too_short" && firstError.ctx?.min_length) {
    return `Password must be at least ${firstError.ctx.min_length} characters.`;
  }
  if ((field === "password" || field === "new_password") && firstError.type === "string_too_long" && firstError.ctx?.max_length) {
    return `Password must be at most ${firstError.ctx.max_length} characters.`;
  }
  if (field === "email") {
    return "Enter a valid email address.";
  }
  if (typeof field === "string") {
    const label = field.charAt(0).toUpperCase() + field.slice(1).replace(/_/g, " ");
    return `${label}: ${firstError.msg}`;
  }
  return firstError.msg;
}

async function apiFetch<T>(path: string, init?: RequestInit, auth = true): Promise<T> {
  const headers = new Headers(init?.headers ?? {});
  headers.set("Content-Type", "application/json");

  if (auth) {
    const token = getAccessToken();
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }
  }

  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    headers,
  });

  if (!response.ok) {
    const responseText = await response.text();
    let message = responseText || `Request failed with status ${response.status}`;
    try {
      const parsed = JSON.parse(responseText) as { detail?: string | ValidationErrorPayload[] };
      if (typeof parsed.detail === "string" && parsed.detail.trim()) {
        message = parsed.detail;
      } else if (Array.isArray(parsed.detail)) {
        message = formatValidationMessage(parsed.detail) ?? message;
      }
    } catch {
      // Fall back to the raw response body.
    }
    throw new Error(message);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const responseText = await response.text();
  if (!responseText) {
    return undefined as T;
  }
  return JSON.parse(responseText) as T;
}

export async function register(payload: {
  fullName: string;
  email: string;
  password: string;
}): Promise<AuthSession> {
  const response = await apiFetch<AuthApiPayload>(
    "/auth/register",
    {
      method: "POST",
      body: JSON.stringify({
        full_name: payload.fullName,
        email: payload.email,
        password: payload.password,
      }),
    },
    false,
  );
  return normalizeAuth(response);
}

export async function login(payload: { email: string; password: string }): Promise<AuthSession> {
  const response = await apiFetch<AuthApiPayload>(
    "/auth/login",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    false,
  );
  return normalizeAuth(response);
}

export async function forgotPassword(payload: {
  email: string;
}): Promise<{ message: string; resetToken: string | null; resetUrl: string | null }> {
  const response = await apiFetch<ForgotPasswordApiPayload>(
    "/auth/forgot-password",
    {
      method: "POST",
      body: JSON.stringify({ email: payload.email }),
    },
    false,
  );
  return {
    message: response.message,
    resetToken: response.reset_token,
    resetUrl: response.reset_url,
  };
}

export async function resetPassword(payload: {
  token: string;
  newPassword: string;
}): Promise<AuthSession> {
  const response = await apiFetch<AuthApiPayload>(
    "/auth/reset-password",
    {
      method: "POST",
      body: JSON.stringify({
        token: payload.token,
        new_password: payload.newPassword,
      }),
    },
    false,
  );
  return normalizeAuth(response);
}

export async function getCurrentUser(): Promise<AuthUser> {
  const response = await apiFetch<AuthApiPayload["user"]>("/auth/me");
  return normalizeUser(response);
}

export async function listProjects(): Promise<ProjectSummary[]> {
  const response = await apiFetch<ProjectSummaryApiPayload[]>("/projects");
  return response.map(normalizeProjectSummary);
}

export async function createProject(payload: {
  name: string;
  initialFileName: string;
  language: Language;
  initialContent: string;
}): Promise<ProjectDetail> {
  const response = await apiFetch<ProjectDetailApiPayload>("/projects", {
    method: "POST",
    body: JSON.stringify({
      name: payload.name,
      initial_file_name: payload.initialFileName,
      language: payload.language,
      initial_content: payload.initialContent,
    }),
  });
  return normalizeProjectDetail(response);
}

export async function deleteProject(projectId: string): Promise<void> {
  await apiFetch<void>(`/projects/${projectId}`, { method: "DELETE" });
}

export async function getProject(projectId: string): Promise<ProjectDetail> {
  const response = await apiFetch<ProjectDetailApiPayload>(`/projects/${projectId}`);
  return normalizeProjectDetail(response);
}

export async function createFile(payload: {
  projectId: string;
  name: string;
  language: Language;
  initialContent: string;
}): Promise<FileRecord> {
  const response = await apiFetch<FileApiPayload>(`/projects/${payload.projectId}/files`, {
    method: "POST",
    body: JSON.stringify({
      name: payload.name,
      language: payload.language,
      initial_content: payload.initialContent,
    }),
  });
  return normalizeFile(response);
}

export async function getFile(fileId: string): Promise<FileRecord> {
  const response = await apiFetch<FileApiPayload>(`/files/${fileId}`);
  return normalizeFile(response);
}

export async function joinFile(fileId: string): Promise<{ projectId: string; fileId: string; shareMode: ShareMode }> {
  const response = await apiFetch<FileJoinApiPayload>(`/files/${fileId}/join`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  return {
    projectId: response.project_id,
    fileId: response.file_id,
    shareMode: response.share_mode,
  };
}

export async function createFileSession(fileId: string): Promise<CollaborationSession> {
  const response = await apiFetch<{
    session_id: string;
    display_name: string;
    color: string;
  }>(`/files/${fileId}/sessions`, {
    method: "POST",
    body: JSON.stringify({}),
  });

  return {
    sessionId: response.session_id,
    displayName: response.display_name,
    color: response.color,
  };
}

export async function executeCode(language: Language, code: string): Promise<ExecutionResult> {
  const response = await apiFetch<{
    language: Language;
    stdout: string;
    stderr: string;
    exit_code: number;
    duration_ms: number;
    timed_out: boolean;
  }>("/execute", {
    method: "POST",
    body: JSON.stringify({ language, code }),
  });

  return {
    language: response.language,
    stdout: response.stdout,
    stderr: response.stderr,
    exitCode: response.exit_code,
    durationMs: response.duration_ms,
    timedOut: response.timed_out,
  };
}

export function buildFileSocketUrl(fileId: string, session: CollaborationSession, token: string): string {
  const url = new URL(`${wsBaseUrl.replace(/\/$/, "")}/files/${fileId}`);
  url.searchParams.set("session_id", session.sessionId);
  url.searchParams.set("color", session.color);
  url.searchParams.set("token", token);
  return url.toString();
}
