import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { createProject, deleteProject, listProjects } from "../lib/api";
import { clearAuthSession } from "../lib/auth";
import { defaultFileNameForLanguage, starterTemplates } from "../lib/templates";
import type { AuthSession, Language, ProjectSummary } from "../types";

type DashboardPageProps = {
  session: AuthSession;
  onSignedOut: () => void;
};

export function DashboardPage({ session, onSignedOut }: DashboardPageProps) {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [projectName, setProjectName] = useState("Realtime Pairing Workspace");
  const [language, setLanguage] = useState<Language>("python");
  const [error, setError] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [deletingProjectId, setDeletingProjectId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listProjects()
      .then((nextProjects) => {
        if (!cancelled) {
          setProjects(nextProjects);
        }
      })
      .catch((caughtError) => {
        if (!cancelled) {
          setError(caughtError instanceof Error ? caughtError.message : "Unable to load projects.");
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  async function handleCreateProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsCreating(true);

    try {
      const project = await createProject({
        name: projectName.trim() || "Untitled Project",
        initialFileName: defaultFileNameForLanguage(language),
        language,
        initialContent: starterTemplates[language],
      });
      setProjects((currentProjects) => [
        {
          id: project.id,
          name: project.name,
          ownerId: project.ownerId,
          shareMode: project.shareMode,
          fileCount: project.files.length,
          defaultFileId: project.files[0]?.id ?? null,
          createdAt: project.createdAt,
          updatedAt: project.updatedAt,
        },
        ...currentProjects,
      ]);
      if (project.files[0]) {
        navigate(`/projects/${project.id}/files/${project.files[0].id}`);
      }
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Unable to create project.");
    } finally {
      setIsCreating(false);
    }
  }

  function handleSignOut() {
    clearAuthSession();
    onSignedOut();
  }

  async function handleDeleteProject(projectId: string) {
    const confirmed = window.confirm("Delete this project and all of its files?");
    if (!confirmed) {
      return;
    }

    setDeletingProjectId(projectId);
    setError(null);
    try {
      await deleteProject(projectId);
      setProjects((currentProjects) => currentProjects.filter((project) => project.id !== projectId));
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Unable to delete project.");
    } finally {
      setDeletingProjectId(null);
    }
  }

  return (
    <main className="dashboard-shell">
      <header className="dashboard-header">
        <div>
          <p className="eyebrow">Workspace</p>
          <h1>{session.user.fullName}'s Projects</h1>
        </div>
        <button type="button" className="ghost-button" onClick={handleSignOut}>
          Sign out
        </button>
      </header>

      <section className="dashboard-grid">
        <section className="panel dashboard-panel">
          <div className="panel-heading">
            <h2>Create Project</h2>
            <span>Persistent collaboration</span>
          </div>
          <form className="create-room-form" onSubmit={handleCreateProject}>
            <label>
              Project name
              <input value={projectName} onChange={(event) => setProjectName(event.target.value)} />
            </label>
            <label>
              Starter language
              <select value={language} onChange={(event) => setLanguage(event.target.value as Language)}>
                <option value="python">Python</option>
                <option value="javascript">JavaScript</option>
                <option value="cpp">C++</option>
              </select>
            </label>
            <button type="submit" disabled={isCreating}>
              {isCreating ? "Creating..." : "Create project"}
            </button>
            {error ? <p className="error-banner">{error}</p> : null}
          </form>
        </section>

        <section className="panel dashboard-panel">
          <div className="panel-heading">
            <h2>Your Projects</h2>
            <span>{projects.length} total</span>
          </div>
          <div className="project-list">
            {projects.map((project) => (
              <div className="project-card" key={project.id}>
                <button
                  type="button"
                  className="project-card-open"
                  onClick={() =>
                    project.defaultFileId
                      ? navigate(`/projects/${project.id}/files/${project.defaultFileId}`)
                      : navigate(`/projects/${project.id}`)
                  }
                >
                  <strong>{project.name}</strong>
                  <span>{project.fileCount} files</span>
                </button>
                {project.ownerId === session.user.id ? (
                  <button
                    type="button"
                    className="ghost-button project-delete-button"
                    onClick={() => void handleDeleteProject(project.id)}
                    disabled={deletingProjectId === project.id}
                  >
                    {deletingProjectId === project.id ? "Deleting..." : "Delete"}
                  </button>
                ) : null}
              </div>
            ))}
            {projects.length === 0 ? <p className="muted">Create your first project to start collaborating.</p> : null}
          </div>
        </section>
      </section>
    </main>
  );
}
