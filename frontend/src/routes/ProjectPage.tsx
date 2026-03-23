import Editor from "@monaco-editor/react";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { OutputPanel } from "../components/OutputPanel";
import { PresenceList } from "../components/PresenceList";
import {
  createFile,
  createFileSession,
  deleteProject,
  executeCode,
  getProject,
  joinFile,
} from "../lib/api";
import { clearAuthSession } from "../lib/auth";
import { defaultFileNameForLanguage, starterTemplates } from "../lib/templates";
import { useCollaborativeFile } from "../hooks/useCollaborativeFile";
import type {
  AuthSession,
  CollaborationSession,
  ExecutionResult,
  Language,
  ProjectDetail,
} from "../types";

type ProjectPageProps = {
  session: AuthSession;
  onSignedOut: () => void;
};

export function ProjectPage({ session, onSignedOut }: ProjectPageProps) {
  const { projectId, fileId } = useParams();
  const navigate = useNavigate();
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [fileSession, setFileSession] = useState<CollaborationSession | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [runResult, setRunResult] = useState<ExecutionResult | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [newFileName, setNewFileName] = useState("main.py");
  const [newFileLanguage, setNewFileLanguage] = useState<Language>("python");
  const [isCreatingFile, setIsCreatingFile] = useState(false);
  const [isDeletingProject, setIsDeletingProject] = useState(false);

  useEffect(() => {
    if (!projectId) {
      navigate("/");
      return;
    }

    const resolvedProjectId = projectId;
    let cancelled = false;
    async function loadProject() {
      setLoadError(null);
      setProject(null);
      setFileSession(null);
      try {
        if (fileId) {
          await joinFile(fileId);
        }
        const projectDetail = await getProject(resolvedProjectId);
        if (cancelled) {
          return;
        }
        setProject(projectDetail);
        if (!fileId && projectDetail.files[0]) {
          navigate(`/projects/${projectDetail.id}/files/${projectDetail.files[0].id}`, { replace: true });
        }
      } catch (caughtError) {
        if (!cancelled) {
          setLoadError(caughtError instanceof Error ? caughtError.message : "Unable to load project.");
        }
      }
    }

    void loadProject();

    return () => {
      cancelled = true;
    };
  }, [fileId, navigate, projectId]);

  const refreshFileSession = useCallback(async () => {
    if (!fileId) {
      return;
    }

    try {
      const nextSession = await createFileSession(fileId);
      setFileSession(nextSession);
    } catch (caughtError) {
      setLoadError(
        caughtError instanceof Error ? caughtError.message : "Unable to create collaboration session.",
      );
    }
  }, [fileId]);

  useEffect(() => {
    if (!fileId || !project) {
      return;
    }
    void refreshFileSession();
  }, [fileId, project?.id, refreshFileSession]);

  const collaboration = useCollaborativeFile(
    fileId,
    session.accessToken,
    fileSession,
    refreshFileSession,
  );

  const activeFile = useMemo(() => {
    if (!project || !fileId) {
      return null;
    }
    return project.files.find((file) => file.id === fileId) ?? null;
  }, [fileId, project]);

  useEffect(() => {
    const nextCollabFile = collaboration.file;
    if (!nextCollabFile) {
      return;
    }

    setProject((currentProject) => {
      if (!currentProject) {
        return currentProject;
      }
      const currentFile = currentProject.files.find((file) => file.id === nextCollabFile.id);
      if (!currentFile || currentFile.language === nextCollabFile.language) {
        return currentProject;
      }
      const nextFiles = currentProject.files.map((file) =>
        file.id === nextCollabFile.id ? { ...file, language: nextCollabFile.language } : file,
      );
      return { ...currentProject, files: nextFiles };
    });
  }, [collaboration.file]);

  async function handleRunCode() {
    setIsRunning(true);
    try {
      const result = await executeCode(collaboration.language, collaboration.getCurrentCode());
      setRunResult(result);
    } catch (caughtError) {
      setRunResult({
        language: collaboration.language,
        stdout: "",
        stderr: caughtError instanceof Error ? caughtError.message : "Unable to run code.",
        exitCode: -1,
        durationMs: 0,
        timedOut: false,
      });
    } finally {
      setIsRunning(false);
    }
  }

  async function handleCreateFile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!projectId) {
      return;
    }

    setIsCreatingFile(true);
    setLoadError(null);
    try {
      const file = await createFile({
        projectId,
        name: newFileName.trim() || defaultFileNameForLanguage(newFileLanguage),
        language: newFileLanguage,
        initialContent: starterTemplates[newFileLanguage],
      });
      setProject((currentProject) =>
        currentProject ? { ...currentProject, files: [...currentProject.files, file] } : currentProject,
      );
      navigate(`/projects/${projectId}/files/${file.id}`);
    } catch (caughtError) {
      setLoadError(caughtError instanceof Error ? caughtError.message : "Unable to create file.");
    } finally {
      setIsCreatingFile(false);
    }
  }

  async function copyFileLink() {
    const url = collaboration.file?.shareUrl ?? window.location.href;
    await navigator.clipboard.writeText(url);
  }

  function handleSignOut() {
    clearAuthSession();
    onSignedOut();
  }

  async function handleDeleteProject() {
    if (!projectId) {
      return;
    }

    const confirmed = window.confirm("Delete this project and all of its files?");
    if (!confirmed) {
      return;
    }

    setIsDeletingProject(true);
    setLoadError(null);
    try {
      await deleteProject(projectId);
      navigate("/", { replace: true });
    } catch (caughtError) {
      setLoadError(caughtError instanceof Error ? caughtError.message : "Unable to delete project.");
    } finally {
      setIsDeletingProject(false);
    }
  }

  if (!projectId) {
    return null;
  }

  if (!project) {
    return <main className="room-loading">{loadError ?? "Loading project..."}</main>;
  }

  return (
    <main className="project-shell">
      <aside className="project-sidebar panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Project</p>
            <h2>{project.name}</h2>
            <p className="muted">
              {project.shareMode === "authenticated_link"
                ? "Any signed-in user with the file link can join."
                : "Private project"}
            </p>
          </div>
          <button type="button" className="ghost-button" onClick={handleSignOut}>
            Sign out
          </button>
        </div>
        {project.ownerId === session.user.id ? (
          <button
            type="button"
            className="ghost-button project-delete-button"
            onClick={() => void handleDeleteProject()}
            disabled={isDeletingProject}
          >
            {isDeletingProject ? "Deleting project..." : "Delete project"}
          </button>
        ) : null}

        <nav className="file-list">
          {project.files.map((file) => (
            <Link
              key={file.id}
              className={`file-link ${file.id === fileId ? "file-link-active" : ""}`}
              to={`/projects/${project.id}/files/${file.id}`}
            >
              <strong>{file.name}</strong>
              <span>{file.language}</span>
            </Link>
          ))}
        </nav>

        <form className="create-room-form" onSubmit={handleCreateFile}>
          <label>
            New file
            <input value={newFileName} onChange={(event) => setNewFileName(event.target.value)} />
          </label>
          <label>
            Language
            <select
              value={newFileLanguage}
              onChange={(event) => setNewFileLanguage(event.target.value as Language)}
            >
              <option value="python">Python</option>
              <option value="javascript">JavaScript</option>
              <option value="cpp">C++</option>
            </select>
          </label>
          <button type="submit" disabled={isCreatingFile}>
            {isCreatingFile ? "Adding..." : "Add file"}
          </button>
        </form>
      </aside>

      <section className="project-main">
        <header className="workspace-header">
          <div>
            <p className="eyebrow">File</p>
            <h1>{activeFile?.name ?? collaboration.file?.name ?? "Loading..."}</h1>
          </div>
          <div className="workspace-actions">
            <span className={`status-pill status-${collaboration.connectionStatus}`}>
              {collaboration.connectionStatus}
            </span>
            <span className="latency-pill">
              sync {collaboration.syncLatencyMs ? `${collaboration.syncLatencyMs} ms` : "pending"}
            </span>
            <button type="button" className="ghost-button" onClick={copyFileLink}>
              Copy link
            </button>
          </div>
        </header>

        <section className="toolbar panel">
          <div className="toolbar-group">
            <label>
              Language
              <select
                value={collaboration.language}
                onChange={(event) => collaboration.changeLanguage(event.target.value as Language)}
              >
                <option value="python">Python</option>
                <option value="javascript">JavaScript</option>
                <option value="cpp">C++</option>
              </select>
            </label>
            <div className="session-chip">
              <strong>{session.user.fullName}</strong>
            </div>
          </div>
          <button type="button" onClick={handleRunCode} disabled={isRunning}>
            {isRunning ? "Running..." : "Run code"}
          </button>
        </section>

        {loadError || collaboration.error ? (
          <p className="error-banner">{loadError ?? collaboration.error}</p>
        ) : null}

        <section className="workspace-grid">
          <section className="editor-panel panel">
            <Editor
              height="72vh"
              theme="vs-dark"
              defaultLanguage={collaboration.language}
              defaultValue=""
              options={{
                minimap: { enabled: false },
                fontSize: 15,
                fontLigatures: true,
                scrollBeyondLastLine: false,
                wordWrap: "on",
              }}
              onMount={collaboration.attachEditor}
            />
          </section>

          <aside className="sidebar-column">
            <PresenceList participants={collaboration.participants} session={fileSession} />
            <OutputPanel result={runResult} isRunning={isRunning} />
          </aside>
        </section>
      </section>
    </main>
  );
}
