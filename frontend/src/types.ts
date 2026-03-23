export type Language = "python" | "javascript" | "cpp";
export type ShareMode = "private" | "authenticated_link";
export type ConnectionStatus = "connecting" | "connected" | "reconnecting" | "disconnected";

export interface AuthUser {
  id: string;
  email: string;
  fullName: string;
  createdAt: string;
}

export interface AuthSession {
  accessToken: string;
  tokenType: string;
  user: AuthUser;
}

export interface ProjectSummary {
  id: string;
  name: string;
  ownerId: string;
  shareMode: ShareMode;
  fileCount: number;
  defaultFileId: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface FileRecord {
  id: string;
  projectId: string;
  name: string;
  language: Language;
  latestStateSize: number;
  createdAt: string;
  updatedAt: string;
  shareUrl: string;
}

export interface ProjectDetail {
  id: string;
  name: string;
  ownerId: string;
  shareMode: ShareMode;
  createdAt: string;
  updatedAt: string;
  files: FileRecord[];
}

export interface CollaborationSession {
  sessionId: string;
  displayName: string;
  color: string;
}

export interface Participant {
  sessionId: string;
  displayName: string;
  color: string;
  connectedAt: string;
  selectionStart: number | null;
  selectionEnd: number | null;
}

export interface ExecutionResult {
  language: Language;
  stdout: string;
  stderr: string;
  exitCode: number;
  durationMs: number;
  timedOut: boolean;
}
