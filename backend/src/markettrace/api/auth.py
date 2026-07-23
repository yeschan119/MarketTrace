"""Login-gated auth for the manual ingest endpoint.

Uses a stdlib-only signed token (no extra dependency):

    token = base64url("<exp_epoch>:<hex_hmac_sha256(auth_secret, exp_epoch)>")

``create_token`` issues a token valid for 12 hours; ``verify_token`` recomputes
the HMAC with :func:`hmac.compare_digest` and rejects expired/malformed tokens.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from markettrace.api import admin_service
from markettrace.api.deps import get_db
from markettrace.api.schemas import CurrentUserOut
from markettrace.config import get_settings
from markettrace.db.models import AdminUser
from markettrace.db.session import make_engine, make_session_factory

__all__ = [
    "AuthPrincipal",
    "router",
    "create_token",
    "create_user_token",
    "verify_token",
    "require_login",
    "require_auth",
    "require_admin",
]

# Token lifetime: 12 hours.
_TOKEN_TTL_SECONDS = 12 * 60 * 60

router = APIRouter()


@dataclass(frozen=True)
class AuthPrincipal:
    user_id: int | None
    login_id: str
    name: str
    email: str | None
    role: str
    legacy: bool = False


def _sign(exp_epoch: int, secret: str) -> str:
    """Return the hex HMAC-SHA256 of ``exp_epoch`` keyed by ``secret``."""
    return hmac.new(
        secret.encode("utf-8"),
        str(exp_epoch).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _sign_bytes(payload: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def create_token() -> str:
    """Mint a signed token valid for 12 hours.

    Raises ``RuntimeError`` if ``auth_secret`` is not configured.
    """
    secret = get_settings().auth_secret
    if not secret:
        raise RuntimeError("auth_secret is not configured")
    exp_epoch = int(time.time()) + _TOKEN_TTL_SECONDS
    payload = f"{exp_epoch}:{_sign(exp_epoch, secret)}"
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


def create_user_token(user: AdminUser) -> str:
    """Mint a signed token for a DB-backed admin-console user."""
    secret = get_settings().auth_secret
    if not secret:
        raise RuntimeError("auth_secret is not configured")
    payload = {
        "kind": "user",
        "sub": user.id,
        "login_id": user.login_id,
        "role": user.role,
        "exp": int(time.time()) + _TOKEN_TTL_SECONDS,
    }
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    encoded = base64.urlsafe_b64encode(payload_bytes).decode("ascii")
    return f"{encoded}.{_sign_bytes(payload_bytes, secret)}"


def decode_token(token: str) -> dict[str, Any] | None:
    """Decode either the legacy env-admin token or the DB-user token."""
    secret = get_settings().auth_secret
    if not secret:
        return None

    if "." in token:
        try:
            payload_b64, signature = token.split(".", 1)
            payload_bytes = base64.urlsafe_b64decode(payload_b64.encode("ascii"))
            expected = _sign_bytes(payload_bytes, secret)
            if not hmac.compare_digest(expected, signature):
                return None
            payload = json.loads(payload_bytes)
            if int(payload.get("exp", 0)) <= int(time.time()):
                return None
            return payload if payload.get("kind") == "user" else None
        except (binascii.Error, UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError):
            return None

    try:
        decoded = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        exp_str, signature = decoded.split(":", 1)
        exp_epoch = int(exp_str)
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None

    expected = _sign(exp_epoch, secret)
    if not hmac.compare_digest(expected, signature):
        return None
    if int(time.time()) >= exp_epoch:
        return None
    return {"kind": "legacy_admin", "role": "admin", "exp": exp_epoch}


def verify_token(token: str) -> bool:
    """Return True if ``token`` is well-formed, unexpired, and correctly signed."""
    return decode_token(token) is not None


def _bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    return authorization[len("Bearer "):]


def require_auth(authorization: str | None = Header(default=None)) -> None:
    """FastAPI dependency: require a valid ``Authorization: Bearer <token>`` header."""
    token = _bearer_token(authorization)
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if payload.get("kind") == "user" and payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")


def require_login(authorization: str | None = Header(default=None)) -> None:
    """FastAPI dependency: require any valid logged-in user token."""
    token = _bearer_token(authorization)
    if decode_token(token) is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def get_current_principal(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> AuthPrincipal:
    token = _bearer_token(authorization)
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    if payload.get("kind") == "legacy_admin":
        settings = get_settings()
        login_id = settings.admin_username or "admin"
        return AuthPrincipal(
            user_id=None,
            login_id=login_id,
            name="Admin",
            email=None,
            role="admin",
            legacy=True,
        )

    user_id = payload.get("sub")
    if not isinstance(user_id, int):
        raise HTTPException(status_code=401, detail="Invalid token subject")
    user = db.get(AdminUser, user_id)
    if user is None or not user.status:
        raise HTTPException(status_code=401, detail="Invalid or inactive user")
    return AuthPrincipal(
        user_id=user.id,
        login_id=user.login_id or "",
        name=user.name,
        email=user.email,
        role=user.role,
        legacy=False,
    )


def require_admin(
    principal: AuthPrincipal = Depends(get_current_principal),
) -> AuthPrincipal:
    if principal.role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return principal


def _try_db_login(username: str, password: str) -> AdminUser | None:
    database_url = getattr(get_settings(), "database_url", None)
    if not database_url:
        return None
    try:
        engine = make_engine(database_url)
        factory = make_session_factory(engine)
        with factory() as db:
            return admin_service.authenticate_user(db, username, password)
    except SQLAlchemyError:
        return None
    finally:
        if "engine" in locals():
            engine.dispose()


@router.post("/auth/login")
def login(payload: dict) -> dict[str, str]:
    """Authenticate admin credentials and return a signed token."""
    settings = get_settings()
    if not settings.auth_secret:
        raise HTTPException(status_code=503, detail="auth not configured")

    username = payload.get("username") or ""
    password = payload.get("password") or ""
    if settings.admin_username and settings.admin_password:
        user_ok = hmac.compare_digest(username, settings.admin_username)
        pass_ok = hmac.compare_digest(password, settings.admin_password)
        if user_ok and pass_ok:
            return {"token": create_token()}

    user = _try_db_login(username, password)
    if user is not None:
        return {"token": create_user_token(user)}

    raise HTTPException(status_code=401, detail="Invalid credentials")


@router.get("/auth/me", response_model=CurrentUserOut)
def me(
    principal: AuthPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> CurrentUserOut:
    try:
        allowed_tabs = admin_service.get_allowed_tabs(db, principal.role)
    except admin_service.AdminServiceError:
        allowed_tabs = []
    return CurrentUserOut(
        id=principal.user_id,
        login_id=principal.login_id,
        name=principal.name,
        email=principal.email,
        role=principal.role,
        legacy=principal.legacy,
        allowed_tabs=allowed_tabs,
    )
