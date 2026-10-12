# CollabCode

A real-time collaborative code editor enabling multiple users to edit code simultaneously with live cursors, conflict-free syncing, and a scalable backend
Google Docs collaboration, VS Code editing, and GitHub-style project ownership in one real-time coding workspace.

CollabCode is a full-stack collaborative editor built with `FastAPI`, `React`, `Monaco`, `Yjs`, `Redis`, and `PostgreSQL`. Users sign in, create persistent projects, edit multiple files, share file links with other signed-in users, and collaborate live with cursor presence, autosave, and conflict-free CRDT sync.

## Why this project matters

Most collaborative editor demos stop at “multiple users can type in the same text box.” This project goes further:

- authenticated users instead of anonymous room links
- persistent projects and files instead of ephemeral sessions
- file-based collaboration on top of a project model
- real WebSocket state sync backed by Redis pub/sub
- CRDT conflict resolution with Yjs
- production-minded features like reconnection handling, password reset, project deletion, metrics, and Dockerized local infrastructure

This is the product model:

```text
Users -> Projects -> Files -> Real-time collaboration per file
```

Not:

```text
Anonymous users -> temporary rooms
```

<img width="1469" height="808" alt="Screenshot 2026-03-23 at 8 18 02 PM" src="https://github.com/user-attachments/assets/f364b22f-7a3c-4db4-ac17-356e8211593d" />

## Core features

- Email/password authentication with per-tab sessions
- Forgot password flow with reset tokens
- Persistent projects owned by users
- Multi-file editing inside each project
- Shareable file links for other signed-in users
- Live cursor and selection presence
- Conflict-free concurrent editing with Yjs CRDT
- Monaco editor with Python, JavaScript, and C++ support
- Code execution panel for supported languages
- Project deletion
- Prometheus metrics and Grafana dashboards
- Docker Compose setup for the full stack

## Tech stack

- Frontend: `React`, `TypeScript`, `Vite`, `Monaco Editor`, `Yjs`
- Backend: `Python`, `FastAPI`, `SQLAlchemy`, `asyncpg`
- Real-time: `WebSockets`, `Redis pub/sub`
- Persistence: `PostgreSQL`
- Monitoring: `Prometheus`, `Grafana`
- Load testing scaffold: `Locust`

## Product model

### Users

Users register, log in, reset passwords, and receive bearer tokens for authenticated API and WebSocket access.

### Projects

Projects are persistent collaborative workspaces. Each project has:

- an owner
- member access records
- one or more code files

### Files

Each file is a collaborative document with:

- a language
- a persisted Yjs snapshot
- shareable URL
- collaborative presence and live editing state

### Sharing

The current sharing mode is:

- any signed-in user with a shared file link can join the project via that file

This keeps the UX simple while still feeling closer to Docs or GitHub than a temporary room model.

## Architecture

```text
React + Monaco + Yjs client
        |
        | REST: auth, projects, files, execution
        | WebSocket: live file collaboration
        v
FastAPI application
        |
        +--> Auth service
        +--> Project/file service
        +--> Collaboration manager
        +--> Code execution service
        |
        +--> Redis pub/sub for cross-instance sync
        +--> PostgreSQL for users, projects, files, memberships, snapshots
        +--> Prometheus metrics
                |
                v
             Grafana
```


## Data model

Main entities:

- `users`
- `projects`
- `project_members`
- `files`
- `file_snapshots`

High-level relationships:

```text
User 1---* Project (owner)
User *---* Project via project_members
Project 1---* File
File 1---* FileSnapshot
```

## Real-time flow

1. User opens a file in a project
2. Frontend ensures the signed-in user has access to the file
3. Frontend creates a collaborative file session
4. Frontend opens a WebSocket connection for that file
5. Backend hydrates the document from the persisted Yjs snapshot
6. Local edits are turned into Yjs updates
7. Updates are broadcast to other clients and other backend instances through Redis
8. Snapshots are periodically persisted back to Postgres


## Local setup

### Prerequisites

- Docker Desktop

### Start everything

```bash
docker compose down --remove-orphans -v
docker compose up --build
```

### Open the app

- App: `http://localhost:5173`
- Backend docs: `http://localhost:8000/docs`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000`

Grafana default credentials:

- username: `admin`
- password: `admin`

## Demo walkthrough

### Single user

1. Open `http://localhost:5173`
2. Register a user
3. Create a project
4. Open the starter file
5. Edit code and run it from the output panel

### Multi-user collaboration

1. Sign in as user A
2. Create a project and open a file
3. Copy the file link
4. Open the file link in a new incognito window or different browser profile
5. Sign in as user B
6. Both users edit the same file and watch live sync and cursor presence

### Password reset

1. Click `Forgot password?`
2. Submit the email
3. In local development, open the returned reset link
4. Set a new password


## Running without Docker

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Load test scaffold

```bash
cd locust
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
locust -f locustfile.py --host http://localhost:8000
```

## Testing and verification

Backend tests live in `backend/tests`.

Lightweight verification used during development:

- `python3 -m compileall backend/app backend/tests`

Planned or scaffolded verification:

- API tests
- execution tests
- Locust load tests
- containerized local integration testing

## Monitoring

The stack includes:

- Prometheus scraping backend metrics
- Grafana dashboards provisioned from the repo

This gives the project an observability story, not just a feature demo.

## Repository structure

```text
backend/     FastAPI app, services, schemas, tests
frontend/    React app, Monaco integration, auth and project UI
locust/      Load-test scaffold
ops/         Prometheus config
grafana/     Provisioned dashboards
```


## Next steps

- explicit collaborator invites and permissions
- commit history and snapshots UI
- branch-based workflows
- file rename/delete UX
- repo import/export
- stronger deployment and production secret handling

