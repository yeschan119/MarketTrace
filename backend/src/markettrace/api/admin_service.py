"""Admin-console services for users, role permissions, and tab status."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from markettrace.db.models import AdminUser, RoleTabPermission, TabStatus

ROLES = ("admin", "manager", "viewer")
ROLE_LABELS = {"admin": "관리자", "manager": "매니저", "viewer": "뷰어"}
ADMIN_ONLY_TABS = {"admin-users", "admin-tabs"}

TAB_GROUPS: list[dict[str, Any]] = [
    {
        "id": "market",
        "label": "시장",
        "tabs": [
            {"id": "nav-search", "label": "검색", "route": "/instruments"},
            {"id": "nav-events", "label": "이벤트", "route": "/events"},
        ],
    },
    {
        "id": "signals",
        "label": "신호",
        "tabs": [
            {"id": "nav-recommendations", "label": "추천종목", "route": "/recommendations"},
            {"id": "nav-rankings", "label": "랭킹", "route": "/rankings"},
            {"id": "nav-screener", "label": "급락", "route": "/screener"},
            {"id": "nav-watchlist", "label": "관심종목", "route": "/watchlist"},
            {"id": "nav-alerts", "label": "알림", "route": "/alerts"},
            {"id": "nav-stats", "label": "통계", "route": "/stats"},
            {"id": "nav-macro", "label": "거시", "route": "/macro"},
        ],
    },
    {
        "id": "finance",
        "label": "재무",
        "tabs": [
            {"id": "nav-ledger", "label": "카드내역", "route": "/ledger"},
            {"id": "nav-passbook", "label": "통장내역", "route": "/passbook"},
        ],
    },
    {
        "id": "admin",
        "label": "관리자",
        "tabs": [
            {
                "id": "admin-users",
                "label": "사용자 관리",
                "route": "/admin",
                "admin_only": True,
            },
            {
                "id": "admin-tabs",
                "label": "탭 관리",
                "route": "/admin",
                "admin_only": True,
            },
        ],
    },
]

TAB_IDS = tuple(tab["id"] for group in TAB_GROUPS for tab in group["tabs"])
TAB_ID_SET = set(TAB_IDS)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
LOGIN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,31}$")
MIN_PASSWORD_LENGTH = 8
HASH_ITERATIONS = 210_000


class AdminServiceError(Exception):
    status_code = 400

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


class AdminConflictError(AdminServiceError):
    status_code = 409


class AdminForbiddenError(AdminServiceError):
    status_code = 403


class AdminNotFoundError(AdminServiceError):
    status_code = 404


def utcnow() -> datetime:
    return datetime.now(UTC)


def normalize_email(email: str | None) -> str:
    return (email or "").strip().lower()


def normalize_login_id(login_id: str | None) -> str:
    return (login_id or "").strip().lower()


def normalize_role(role: str | None) -> str:
    normalized = (role or "viewer").strip().lower()
    if normalized not in ROLES:
        raise AdminServiceError("role must be admin, manager, or viewer")
    return normalized


def validate_email(email: str) -> None:
    if not EMAIL_RE.fullmatch(email):
        raise AdminServiceError("invalid email")


def validate_login_id(login_id: str) -> None:
    if not LOGIN_ID_RE.fullmatch(login_id):
        raise AdminServiceError("login_id must be 3-32 lowercase letters, numbers, ._-")


def validate_password(password: str) -> None:
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise AdminServiceError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")


def hash_password(password: str) -> str:
    validate_password(password)
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("ascii"), HASH_ITERATIONS
    ).hex()
    return f"pbkdf2_sha256${HASH_ITERATIONS}${salt}${digest}"


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        algorithm, iterations, salt, expected = password_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("ascii"), int(iterations)
        ).hex()
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest, expected)


def to_user_dict(user: AdminUser) -> dict[str, Any]:
    return {
        "id": user.id,
        "login_id": user.login_id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "status": user.status,
        "has_password": bool(user.password_hash),
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "last_login_at": user.last_login_at,
    }


def list_users(db: Session) -> list[dict[str, Any]]:
    users = db.scalars(select(AdminUser).order_by(AdminUser.id.asc())).all()
    return [to_user_dict(user) for user in users]


def get_user_or_raise(db: Session, user_id: int) -> AdminUser:
    user = db.get(AdminUser, user_id)
    if user is None:
        raise AdminNotFoundError("user not found")
    return user


def create_user(
    db: Session,
    *,
    name: str,
    email: str,
    role: str = "viewer",
    status: bool = True,
    login_id: str | None = None,
    password: str | None = None,
) -> dict[str, Any]:
    normalized_email = normalize_email(email)
    normalized_login_id = normalize_login_id(login_id) or None
    clean_name = (name or "").strip()
    if not clean_name:
        raise AdminServiceError("name is required")
    validate_email(normalized_email)
    if normalized_login_id:
        validate_login_id(normalized_login_id)
    if password and not normalized_login_id:
        raise AdminServiceError("login_id is required when setting a password")

    if db.scalar(select(AdminUser).where(func.lower(AdminUser.email) == normalized_email)):
        raise AdminConflictError("email already exists")
    if normalized_login_id and db.scalar(
        select(AdminUser).where(func.lower(AdminUser.login_id) == normalized_login_id)
    ):
        raise AdminConflictError("login_id already exists")

    now = utcnow()
    user = AdminUser(
        login_id=normalized_login_id,
        password_hash=hash_password(password) if password else None,
        name=clean_name,
        email=normalized_email,
        role=normalize_role(role),
        status=bool(status),
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return to_user_dict(user)


def update_user(db: Session, user_id: int, **kwargs: Any) -> dict[str, Any]:
    user = get_user_or_raise(db, user_id)

    if "name" in kwargs and kwargs["name"] is not None:
        clean_name = str(kwargs["name"]).strip()
        if not clean_name:
            raise AdminServiceError("name is required")
        user.name = clean_name
    if "email" in kwargs and kwargs["email"] is not None:
        normalized_email = normalize_email(str(kwargs["email"]))
        validate_email(normalized_email)
        existing = db.scalar(
            select(AdminUser).where(
                func.lower(AdminUser.email) == normalized_email,
                AdminUser.id != user.id,
            )
        )
        if existing:
            raise AdminConflictError("email already exists")
        user.email = normalized_email
    if "role" in kwargs and kwargs["role"] is not None:
        next_role = normalize_role(str(kwargs["role"]))
        validate_role_change(db, user, next_role)
        user.role = next_role
    if "status" in kwargs and kwargs["status"] is not None:
        next_status = bool(kwargs["status"])
        validate_status_change(db, user, next_status)
        user.status = next_status
    if kwargs.get("reset_password"):
        user.password_hash = None
    if "login_id" in kwargs and kwargs["login_id"] is not None:
        normalized_login_id = normalize_login_id(str(kwargs["login_id"])) or None
        if normalized_login_id:
            validate_login_id(normalized_login_id)
            existing = db.scalar(
                select(AdminUser).where(
                    func.lower(AdminUser.login_id) == normalized_login_id,
                    AdminUser.id != user.id,
                )
            )
            if existing:
                raise AdminConflictError("login_id already exists")
        user.login_id = normalized_login_id
    if "password" in kwargs and kwargs["password"]:
        if not user.login_id:
            raise AdminServiceError("login_id is required when setting a password")
        user.password_hash = hash_password(str(kwargs["password"]))

    user.updated_at = utcnow()
    db.commit()
    db.refresh(user)
    return to_user_dict(user)


def delete_user(db: Session, user_id: int, *, current_user_id: int | None = None) -> None:
    if current_user_id == user_id:
        raise AdminForbiddenError("cannot delete your own account")
    user = get_user_or_raise(db, user_id)
    if user.role == "admin" and user.status:
        ensure_another_active_admin(db, user.id)
    db.delete(user)
    db.commit()


def validate_role_change(db: Session, user: AdminUser, next_role: str) -> None:
    if user.role == "admin" and next_role != "admin":
        ensure_another_active_admin(db, user.id)


def validate_status_change(db: Session, user: AdminUser, next_status: bool) -> None:
    if user.role == "admin" and user.status and not next_status:
        ensure_another_active_admin(db, user.id)


def ensure_another_active_admin(db: Session, user_id: int) -> None:
    other = db.scalar(
        select(AdminUser).where(
            AdminUser.id != user_id,
            AdminUser.role == "admin",
            AdminUser.status.is_(True),
        )
    )
    if other is None:
        raise AdminForbiddenError("last active admin account cannot be changed")


def authenticate_user(db: Session, login_id: str, password: str) -> AdminUser | None:
    normalized = normalize_login_id(login_id)
    if not normalized:
        return None
    user = db.scalar(
        select(AdminUser).where(
            func.lower(AdminUser.login_id) == normalized,
            AdminUser.status.is_(True),
        )
    )
    if user is None or not verify_password(password, user.password_hash):
        return None
    now = utcnow()
    user.last_login_at = now
    user.updated_at = now
    db.commit()
    db.refresh(user)
    return user


def list_role_permissions(db: Session) -> dict[str, Any]:
    ensure_role_permission_rows(db)
    permission_map = load_permission_map(db)
    return {
        "roles": [{"value": role, "label": ROLE_LABELS[role]} for role in ROLES],
        "groups": TAB_GROUPS,
        "permissions": [
            {"role": role, "tab_id": tab_id, "can_view": permission_map[role][tab_id]}
            for role in ROLES
            for tab_id in TAB_IDS
        ],
    }


def get_allowed_tabs(db: Session, role: str) -> list[str]:
    normalized = normalize_role(role)
    if normalized == "admin":
        return list(TAB_IDS)
    permission_map = load_permission_map(db)
    return [
        tab_id
        for tab_id in TAB_IDS
        if permission_map[normalized][tab_id] and tab_id not in ADMIN_ONLY_TABS
    ]


def replace_role_permissions(db: Session, permissions: list[dict[str, Any]]) -> dict[str, Any]:
    ensure_role_permission_rows(db)
    permission_map = load_permission_map(db)
    for item in permissions:
        role = normalize_role(item.get("role"))
        tab_id = normalize_tab_id(item.get("tab_id"))
        permission_map[role][tab_id] = normalize_can_view(role, tab_id, item.get("can_view"))
    validate_each_role_has_visible_tab(permission_map)

    now = utcnow()
    rows = {
        (row.role, row.tab_id): row
        for row in db.scalars(select(RoleTabPermission)).all()
    }
    for role in ROLES:
        for tab_id in TAB_IDS:
            row = rows.get((role, tab_id))
            if row is None:
                row = RoleTabPermission(role=role, tab_id=tab_id, updated_at=now)
                db.add(row)
            row.can_view = permission_map[role][tab_id]
            row.updated_at = now
    db.commit()
    return list_role_permissions(db)


def ensure_role_permission_rows(db: Session) -> None:
    existing = {
        (row.role, row.tab_id)
        for row in db.scalars(select(RoleTabPermission)).all()
    }
    now = utcnow()
    changed = False
    for role in ROLES:
        for tab_id in TAB_IDS:
            if (role, tab_id) not in existing:
                db.add(
                    RoleTabPermission(
                        role=role,
                        tab_id=tab_id,
                        can_view=default_can_view(role, tab_id),
                        updated_at=now,
                    )
                )
                changed = True
    if changed:
        db.commit()


def load_permission_map(db: Session) -> dict[str, dict[str, bool]]:
    permission_map = {
        role: {tab_id: default_can_view(role, tab_id) for tab_id in TAB_IDS}
        for role in ROLES
    }
    for row in db.scalars(select(RoleTabPermission)).all():
        if row.role in ROLES and row.tab_id in TAB_ID_SET:
            permission_map[row.role][row.tab_id] = normalize_can_view(
                row.role, row.tab_id, row.can_view
            )
    return permission_map


def default_can_view(role: str, tab_id: str) -> bool:
    if role == "admin":
        return True
    if tab_id in ADMIN_ONLY_TABS:
        return False
    return role in ROLES


def normalize_tab_id(tab_id: str | None) -> str:
    normalized = (tab_id or "").strip()
    if normalized not in TAB_ID_SET:
        raise AdminServiceError(f"unknown tab id: {normalized}")
    return normalized


def normalize_can_view(role: str, tab_id: str, can_view: Any) -> bool:
    if role == "admin":
        return True
    if tab_id in ADMIN_ONLY_TABS:
        return False
    return bool(can_view)


def validate_each_role_has_visible_tab(permission_map: dict[str, dict[str, bool]]) -> None:
    for role, permissions in permission_map.items():
        if role == "admin":
            continue
        if not any(permissions.values()):
            raise AdminServiceError(f"{ROLE_LABELS[role]} role must have at least one visible tab")


def list_tab_statuses(db: Session) -> dict[str, bool]:
    rows = {row.tab_id: row.in_use for row in db.scalars(select(TabStatus)).all()}
    return {tab_id: bool(rows.get(tab_id, True)) for tab_id in TAB_IDS}


def set_tab_statuses(db: Session, updates: dict[str, bool]) -> dict[str, bool]:
    if not updates:
        return list_tab_statuses(db)
    clean_updates = {normalize_tab_id(tab_id): bool(value) for tab_id, value in updates.items()}
    existing = {
        row.tab_id: row
        for row in db.scalars(
            select(TabStatus).where(TabStatus.tab_id.in_(clean_updates.keys()))
        ).all()
    }
    now = utcnow()
    for tab_id, in_use in clean_updates.items():
        row = existing.get(tab_id)
        if row is None:
            db.add(TabStatus(tab_id=tab_id, in_use=in_use, updated_at=now))
        else:
            row.in_use = in_use
            row.updated_at = now
    db.commit()
    return list_tab_statuses(db)


def get_tab_catalog(db: Session) -> dict[str, Any]:
    return {"groups": TAB_GROUPS, "statuses": list_tab_statuses(db)}
