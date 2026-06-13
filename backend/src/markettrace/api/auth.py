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
import time

from fastapi import APIRouter, Header, HTTPException

from markettrace.config import get_settings

__all__ = ["router", "create_token", "verify_token", "require_auth"]

# Token lifetime: 12 hours.
_TOKEN_TTL_SECONDS = 12 * 60 * 60

router = APIRouter()


def _sign(exp_epoch: int, secret: str) -> str:
    """Return the hex HMAC-SHA256 of ``exp_epoch`` keyed by ``secret``."""
    return hmac.new(
        secret.encode("utf-8"),
        str(exp_epoch).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


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


def verify_token(token: str) -> bool:
    """Return True if ``token`` is well-formed, unexpired, and correctly signed."""
    secret = get_settings().auth_secret
    if not secret:
        return False
    try:
        decoded = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        exp_str, signature = decoded.split(":", 1)
        exp_epoch = int(exp_str)
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return False

    expected = _sign(exp_epoch, secret)
    if not hmac.compare_digest(expected, signature):
        return False
    return int(time.time()) < exp_epoch


def require_auth(authorization: str | None = Header(default=None)) -> None:
    """FastAPI dependency: require a valid ``Authorization: Bearer <token>`` header."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization[len("Bearer "):]
    if not verify_token(token):
        raise HTTPException(status_code=401, detail="Invalid or expired token")


@router.post("/auth/login")
def login(payload: dict) -> dict[str, str]:
    """Authenticate admin credentials and return a signed token."""
    settings = get_settings()
    if not (settings.admin_username and settings.admin_password and settings.auth_secret):
        raise HTTPException(status_code=503, detail="auth not configured")

    username = payload.get("username") or ""
    password = payload.get("password") or ""
    user_ok = hmac.compare_digest(username, settings.admin_username)
    pass_ok = hmac.compare_digest(password, settings.admin_password)
    if not (user_ok and pass_ok):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return {"token": create_token()}
