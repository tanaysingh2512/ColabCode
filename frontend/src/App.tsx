import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";

import { loadAuthSession } from "./lib/auth";
import { useState } from "react";
import type { ReactElement } from "react";
import { AuthPage } from "./routes/AuthPage";
import { DashboardPage } from "./routes/DashboardPage";
import { ProjectPage } from "./routes/ProjectPage";
import type { AuthSession } from "./types";

type ProtectedRouteProps = {
  session: AuthSession | null;
  children: ReactElement;
};

function ProtectedRoute({ session, children }: ProtectedRouteProps) {
  const location = useLocation();
  if (!session) {
    const from = `${location.pathname}${location.search}${location.hash}`;
    return <Navigate to="/auth" replace state={{ from }} />;
  }
  return children;
}

export default function App() {
  const [session, setSession] = useState<AuthSession | null>(() => loadAuthSession());

  return (
    <BrowserRouter>
      <Routes>
        <Route
          path="/auth"
          element={
            session ? <Navigate to="/" replace /> : <AuthPage onAuthenticated={(next) => setSession(next)} />
          }
        />
        <Route
          path="/"
          element={
            <ProtectedRoute session={session}>
              <DashboardPage session={session!} onSignedOut={() => setSession(null)} />
            </ProtectedRoute>
          }
        />
        <Route
          path="/projects/:projectId"
          element={
            <ProtectedRoute session={session}>
              <ProjectPage session={session!} onSignedOut={() => setSession(null)} />
            </ProtectedRoute>
          }
        />
        <Route
          path="/projects/:projectId/files/:fileId"
          element={
            <ProtectedRoute session={session}>
              <ProjectPage session={session!} onSignedOut={() => setSession(null)} />
            </ProtectedRoute>
          }
        />
      </Routes>
    </BrowserRouter>
  );
}
