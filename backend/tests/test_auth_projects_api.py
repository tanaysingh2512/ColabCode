from __future__ import annotations

from fastapi.testclient import TestClient


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_register_create_project_and_file_session(client: TestClient) -> None:
    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "tanay@example.com",
            "full_name": "Tanay Singh",
            "password": "supersecure123",
        },
    )
    assert register_response.status_code == 201
    auth_payload = register_response.json()
    token = auth_payload["access_token"]

    me_response = client.get("/api/v1/auth/me", headers=auth_headers(token))
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "tanay@example.com"

    create_project_response = client.post(
        "/api/v1/projects",
        headers=auth_headers(token),
        json={
            "name": "Realtime IDE",
            "initial_file_name": "main.py",
            "language": "python",
            "initial_content": "print('hello')\n",
        },
    )
    assert create_project_response.status_code == 201
    project = create_project_response.json()
    assert project["name"] == "Realtime IDE"
    assert len(project["files"]) == 1
    file_id = project["files"][0]["id"]

    list_projects_response = client.get("/api/v1/projects", headers=auth_headers(token))
    assert list_projects_response.status_code == 200
    assert list_projects_response.json()[0]["default_file_id"] == file_id

    file_response = client.get(f"/api/v1/files/{file_id}", headers=auth_headers(token))
    assert file_response.status_code == 200
    assert file_response.json()["name"] == "main.py"

    new_file_response = client.post(
        f"/api/v1/projects/{project['id']}/files",
        headers=auth_headers(token),
        json={
            "name": "utils.py",
            "language": "python",
            "initial_content": "def add(a, b):\n    return a + b\n",
        },
    )
    assert new_file_response.status_code == 201

    file_session_response = client.post(
        f"/api/v1/files/{file_id}/sessions",
        headers=auth_headers(token),
    )
    assert file_session_response.status_code == 200
    session_payload = file_session_response.json()
    assert session_payload["display_name"] == "Tanay Singh"
    assert session_payload["session_id"]
    assert session_payload["color"].startswith("#")

    second_user_response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "rishi@example.com",
            "full_name": "Rishi Kumar",
            "password": "supersecure123",
        },
    )
    assert second_user_response.status_code == 201
    second_token = second_user_response.json()["access_token"]

    join_response = client.post(
        f"/api/v1/files/{file_id}/join",
        headers=auth_headers(second_token),
    )
    assert join_response.status_code == 200
    assert join_response.json()["project_id"] == project["id"]

    shared_project_response = client.get(
        f"/api/v1/projects/{project['id']}",
        headers=auth_headers(second_token),
    )
    assert shared_project_response.status_code == 200
    assert shared_project_response.json()["files"][0]["id"] == file_id

    forgot_password_response = client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "tanay@example.com"},
    )
    assert forgot_password_response.status_code == 200
    reset_token = forgot_password_response.json()["reset_token"]
    assert reset_token

    reset_password_response = client.post(
        "/api/v1/auth/reset-password",
        json={
            "token": reset_token,
            "new_password": "newsupersecure123",
        },
    )
    assert reset_password_response.status_code == 200

    relogin_response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "tanay@example.com",
            "password": "newsupersecure123",
        },
    )
    assert relogin_response.status_code == 200

    delete_project_response = client.delete(
        f"/api/v1/projects/{project['id']}",
        headers=auth_headers(token),
    )
    assert delete_project_response.status_code == 204

    deleted_project_response = client.get(
        f"/api/v1/projects/{project['id']}",
        headers=auth_headers(token),
    )
    assert deleted_project_response.status_code == 404
