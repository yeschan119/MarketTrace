"""Tests for the 관리자 tab API: users, role permissions, tab status, and /auth/me."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from markettrace.api import admin_service
from markettrace.api.auth import create_token, create_user_token
from markettrace.api.deps import get_db
from markettrace.api.main import create_app
from markettrace.db.models import Base


class _Settings:
    admin_username = "envadmin"
    admin_password = "envpass"
    auth_secret = "testsecret123"
    cors_allow_origins = "http://localhost:3000"
    database_url = "sqlite+pysqlite:///:memory:"

    @property
    def cors_origins_list(self) -> list[str]:
        return ["http://localhost:3000"]


@pytest.fixture
def settings() -> _Settings:
    return _Settings()


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = factory()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def client(monkeypatch, settings: _Settings, session: Session) -> Iterator[TestClient]:
    monkeypatch.setattr("markettrace.api.auth.get_settings", lambda: settings)
    monkeypatch.setattr("markettrace.api.main.get_settings", lambda: settings)
    app = create_app()

    def override_get_db() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c


@pytest.fixture
def token(monkeypatch, settings: _Settings) -> str:
    monkeypatch.setattr("markettrace.api.auth.get_settings", lambda: settings)
    return create_token()


def test_auth_me_legacy_admin(client: TestClient, token: str) -> None:
    resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "admin"
    assert body["legacy"] is True
    assert "admin-users" in body["allowed_tabs"]


def test_db_user_can_login_and_load_me(monkeypatch, tmp_path) -> None:
    settings = _Settings()
    settings.database_url = f"sqlite+pysqlite:///{tmp_path / 'admin-auth.db'}"
    monkeypatch.setattr("markettrace.api.auth.get_settings", lambda: settings)
    monkeypatch.setattr("markettrace.api.main.get_settings", lambda: settings)
    monkeypatch.setattr("markettrace.api.deps.get_settings", lambda: settings)

    engine = create_engine(settings.database_url)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as db:
        admin_service.create_user(
            db,
            name="Manager",
            email="manager@example.com",
            login_id="manager1",
            password="strongpass1",
            role="manager",
        )

    app = create_app()
    with TestClient(app) as c:
        login_resp = c.post(
            "/auth/login",
            json={"username": "manager1", "password": "strongpass1"},
        )
        assert login_resp.status_code == 200
        user_token = login_resp.json()["token"]

        me_resp = c.get("/auth/me", headers={"Authorization": f"Bearer {user_token}"})
        assert me_resp.status_code == 200
        body = me_resp.json()
        assert body["role"] == "manager"
        assert body["legacy"] is False
        assert "admin-users" not in body["allowed_tabs"]
        assert "nav-events" in body["allowed_tabs"]

    Base.metadata.drop_all(engine)
    engine.dispose()


def test_admin_user_crud(client: TestClient, token: str) -> None:
    create_resp = client.post(
        "/admin/users",
        json={
            "name": "Jane Manager",
            "email": "jane@example.com",
            "login_id": "jane.manager",
            "password": "strongpass1",
            "role": "manager",
            "status": True,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_resp.status_code == 200
    created = create_resp.json()
    assert created["login_id"] == "jane.manager"
    assert created["has_password"] is True

    list_resp = client.get("/admin/users", headers={"Authorization": f"Bearer {token}"})
    assert list_resp.status_code == 200
    assert [u["email"] for u in list_resp.json()["users"]] == ["jane@example.com"]

    update_resp = client.put(
        f"/admin/users/{created['id']}",
        json={"role": "viewer", "reset_password": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["role"] == "viewer"
    assert updated["has_password"] is False

    delete_resp = client.delete(
        f"/admin/users/{created['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert delete_resp.status_code == 204


def test_non_admin_db_user_cannot_manage_users(
    client: TestClient,
    monkeypatch,
    settings: _Settings,
    session: Session,
) -> None:
    monkeypatch.setattr("markettrace.api.auth.get_settings", lambda: settings)
    created = admin_service.create_user(
        session,
        name="Viewer",
        email="viewer@example.com",
        login_id="viewer1",
        password="strongpass1",
        role="viewer",
    )
    user = admin_service.get_user_or_raise(session, created["id"])
    viewer_token = create_user_token(user)

    resp = client.get("/admin/users", headers={"Authorization": f"Bearer {viewer_token}"})
    assert resp.status_code == 403

    write_resp = client.post("/ingest", headers={"Authorization": f"Bearer {viewer_token}"})
    assert write_resp.status_code == 403


def test_role_permissions_lock_admin_only_tabs(client: TestClient, token: str) -> None:
    matrix = client.get(
        "/admin/role-permissions",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    updates = matrix["permissions"] + [
        {"role": "viewer", "tab_id": "admin-users", "can_view": True},
        {"role": "viewer", "tab_id": "nav-events", "can_view": False},
    ]

    resp = client.put(
        "/admin/role-permissions",
        json={"permissions": updates},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    permissions = {
        (item["role"], item["tab_id"]): item["can_view"]
        for item in resp.json()["permissions"]
    }
    assert permissions[("viewer", "admin-users")] is False
    assert permissions[("viewer", "nav-events")] is False
    assert permissions[("admin", "admin-users")] is True


def test_tab_status_update(client: TestClient, token: str) -> None:
    initial = client.get("/tabs").json()
    assert initial["statuses"]["nav-rankings"] is True

    resp = client.put(
        "/admin/tab-status",
        json={"statuses": {"nav-rankings": False}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["statuses"]["nav-rankings"] is False

    followup = client.get("/tabs").json()
    assert followup["statuses"]["nav-rankings"] is False
