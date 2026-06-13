"""Tests for /auth/login and token utilities (create_token, verify_token)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from markettrace.api.auth import create_token, verify_token
from markettrace.api.main import create_app


class _AuthSettings:
    admin_username = "testadmin"
    admin_password = "testpass"
    auth_secret = "testsecret123"
    cors_allow_origins = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return ["http://localhost:3000"]


class _NoAuthSettings:
    admin_username = None
    admin_password = None
    auth_secret = None
    cors_allow_origins = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return ["http://localhost:3000"]


@pytest.fixture
def auth_settings() -> _AuthSettings:
    return _AuthSettings()


@pytest.fixture
def auth_client(monkeypatch, auth_settings: _AuthSettings) -> TestClient:
    monkeypatch.setattr("markettrace.api.auth.get_settings", lambda: auth_settings)
    monkeypatch.setattr("markettrace.api.main.get_settings", lambda: auth_settings)
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def no_auth_client(monkeypatch) -> TestClient:
    s = _NoAuthSettings()
    monkeypatch.setattr("markettrace.api.auth.get_settings", lambda: s)
    monkeypatch.setattr("markettrace.api.main.get_settings", lambda: s)
    app = create_app()
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------


def test_login_success(auth_client: TestClient) -> None:
    resp = auth_client.post("/auth/login", json={"username": "testadmin", "password": "testpass"})
    assert resp.status_code == 200
    data = resp.json()
    assert "token" in data
    assert len(data["token"]) > 0


def test_login_wrong_password(auth_client: TestClient) -> None:
    resp = auth_client.post("/auth/login", json={"username": "testadmin", "password": "wrong"})
    assert resp.status_code == 401


def test_login_wrong_username(auth_client: TestClient) -> None:
    resp = auth_client.post("/auth/login", json={"username": "baduser", "password": "testpass"})
    assert resp.status_code == 401


def test_login_not_configured(no_auth_client: TestClient) -> None:
    resp = no_auth_client.post("/auth/login", json={"username": "admin", "password": "secret"})
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# create_token / verify_token (unit tests)
# ---------------------------------------------------------------------------


def test_verify_token_valid(monkeypatch, auth_settings: _AuthSettings) -> None:
    monkeypatch.setattr("markettrace.api.auth.get_settings", lambda: auth_settings)
    token = create_token()
    assert verify_token(token) is True


def test_verify_token_garbage(monkeypatch, auth_settings: _AuthSettings) -> None:
    monkeypatch.setattr("markettrace.api.auth.get_settings", lambda: auth_settings)
    assert verify_token("notavalidtoken!!") is False


def test_verify_token_tampered(monkeypatch, auth_settings: _AuthSettings) -> None:
    monkeypatch.setattr("markettrace.api.auth.get_settings", lambda: auth_settings)
    token = create_token()
    tampered = token[:-4] + "xxxx"
    assert verify_token(tampered) is False
