"""Admin-console API: users, role permissions, and tab status."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from markettrace.api import admin_service
from markettrace.api.auth import AuthPrincipal, require_admin
from markettrace.api.deps import get_db
from markettrace.api.schemas import (
    AdminUserCreate,
    AdminUserListOut,
    AdminUserOut,
    AdminUserUpdate,
    OkOut,
    RolePermissionMatrixOut,
    RolePermissionUpdateRequest,
    TabCatalogOut,
    TabStatusUpdateRequest,
)

router = APIRouter()


def _raise_admin_error(exc: admin_service.AdminServiceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get("/tabs", response_model=TabCatalogOut)
def get_tab_catalog(db: Session = Depends(get_db)) -> dict:
    """Return the public tab catalog and global on/off state."""
    return admin_service.get_tab_catalog(db)


@router.get("/admin/users", response_model=AdminUserListOut)
def list_admin_users(
    db: Session = Depends(get_db),
    _: AuthPrincipal = Depends(require_admin),
) -> dict:
    return {"users": admin_service.list_users(db)}


@router.post("/admin/users", response_model=AdminUserOut)
def create_admin_user(
    payload: AdminUserCreate,
    db: Session = Depends(get_db),
    _: AuthPrincipal = Depends(require_admin),
) -> dict:
    try:
        return admin_service.create_user(db, **payload.model_dump())
    except admin_service.AdminServiceError as exc:
        _raise_admin_error(exc)


@router.put("/admin/users/{user_id}", response_model=AdminUserOut)
def update_admin_user(
    user_id: int,
    payload: AdminUserUpdate,
    db: Session = Depends(get_db),
    _: AuthPrincipal = Depends(require_admin),
) -> dict:
    try:
        return admin_service.update_user(
            db, user_id, **payload.model_dump(exclude_unset=True)
        )
    except admin_service.AdminServiceError as exc:
        _raise_admin_error(exc)


@router.delete("/admin/users/{user_id}", status_code=204)
def delete_admin_user(
    user_id: int,
    db: Session = Depends(get_db),
    principal: AuthPrincipal = Depends(require_admin),
) -> None:
    try:
        admin_service.delete_user(db, user_id, current_user_id=principal.user_id)
    except admin_service.AdminServiceError as exc:
        _raise_admin_error(exc)


@router.get("/admin/role-permissions", response_model=RolePermissionMatrixOut)
def get_role_permissions(
    db: Session = Depends(get_db),
    _: AuthPrincipal = Depends(require_admin),
) -> dict:
    try:
        return admin_service.list_role_permissions(db)
    except admin_service.AdminServiceError as exc:
        _raise_admin_error(exc)


@router.put("/admin/role-permissions", response_model=RolePermissionMatrixOut)
def update_role_permissions(
    payload: RolePermissionUpdateRequest,
    db: Session = Depends(get_db),
    _: AuthPrincipal = Depends(require_admin),
) -> dict:
    try:
        return admin_service.replace_role_permissions(
            db, [item.model_dump() for item in payload.permissions]
        )
    except admin_service.AdminServiceError as exc:
        _raise_admin_error(exc)


@router.put("/admin/tab-status", response_model=TabCatalogOut)
def update_tab_status(
    payload: TabStatusUpdateRequest,
    db: Session = Depends(get_db),
    _: AuthPrincipal = Depends(require_admin),
) -> dict:
    try:
        statuses = admin_service.set_tab_statuses(db, payload.statuses)
        return {"groups": admin_service.TAB_GROUPS, "statuses": statuses}
    except admin_service.AdminServiceError as exc:
        _raise_admin_error(exc)


@router.post("/admin/role-permissions/seed", response_model=OkOut)
def seed_role_permissions(
    db: Session = Depends(get_db),
    _: AuthPrincipal = Depends(require_admin),
) -> OkOut:
    """Idempotent seed helper used by tests and manual repair."""
    admin_service.ensure_role_permission_rows(db)
    return OkOut()
