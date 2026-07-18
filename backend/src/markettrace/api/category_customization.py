"""Shared login-gated routes for customizing ledger / passbook categories.

Both the card ledger and the bank passbook expose the same customization
surface — per-entry overrides, keyword rules, and user-created categories — so
the routes are built once by :func:`build_customization_router` and mounted
twice, once per domain.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from markettrace.api.auth import require_auth
from markettrace.api.deps import get_db
from markettrace.api.schemas import (
    CategoryCustomizationOut,
    CategoryOverrideRequest,
    CategoryRuleRequest,
    CustomCategoryRequest,
)
from markettrace.ledger import customization


def _customization_state(db: Session, domain: str) -> CategoryCustomizationOut:
    return CategoryCustomizationOut(
        available_categories=[
            {"name": item.name, "source": item.source}
            for item in customization.available_categories(db, domain)
        ],
        rules=[
            {"id": rule.id, "keyword": rule.keyword, "category": rule.category}
            for rule in customization.list_rules(db, domain)
        ],
        overrides=[
            {
                "entry_key": override.entry_key,
                "category": override.category,
                "description": override.description,
            }
            for override in customization.list_overrides(db, domain)
        ],
    )


def build_customization_router(domain: str, prefix: str) -> APIRouter:
    """Return a router exposing the category-customization CRUD for one domain."""
    router = APIRouter()

    @router.get(f"{prefix}/customization", response_model=CategoryCustomizationOut)
    def get_customization(
        _: None = Depends(require_auth),
        db: Session = Depends(get_db),
    ) -> CategoryCustomizationOut:
        """Return available categories, keyword rules, and per-entry overrides."""
        return _customization_state(db, domain)

    @router.put(
        f"{prefix}/customization/override", response_model=CategoryCustomizationOut
    )
    def set_override(
        payload: CategoryOverrideRequest,
        _: None = Depends(require_auth),
        db: Session = Depends(get_db),
    ) -> CategoryCustomizationOut:
        """Assign one transaction to a category, or clear it (``category`` null)."""
        try:
            if payload.category is None:
                customization.clear_override(db, domain, payload.entry_key)
            else:
                customization.set_override(
                    db,
                    domain,
                    entry_key=payload.entry_key,
                    category=payload.category,
                    description=payload.description,
                )
        except customization.CustomizationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _customization_state(db, domain)

    @router.post(
        f"{prefix}/customization/rule", response_model=CategoryCustomizationOut
    )
    def create_rule(
        payload: CategoryRuleRequest,
        _: None = Depends(require_auth),
        db: Session = Depends(get_db),
    ) -> CategoryCustomizationOut:
        """Create/update a keyword→category rule applied to every statement."""
        try:
            customization.create_rule(
                db, domain, keyword=payload.keyword, category=payload.category
            )
        except customization.CustomizationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _customization_state(db, domain)

    @router.delete(
        f"{prefix}/customization/rule/{{rule_id}}",
        response_model=CategoryCustomizationOut,
    )
    def delete_rule(
        rule_id: int,
        _: None = Depends(require_auth),
        db: Session = Depends(get_db),
    ) -> CategoryCustomizationOut:
        if not customization.delete_rule(db, domain, rule_id):
            raise HTTPException(status_code=404, detail="rule not found")
        return _customization_state(db, domain)

    @router.post(
        f"{prefix}/customization/category", response_model=CategoryCustomizationOut
    )
    def create_category(
        payload: CustomCategoryRequest,
        _: None = Depends(require_auth),
        db: Session = Depends(get_db),
    ) -> CategoryCustomizationOut:
        """Create a new custom category available for reassignment."""
        try:
            customization.create_custom_category(db, domain, name=payload.name)
        except customization.CustomizationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _customization_state(db, domain)

    @router.delete(
        f"{prefix}/customization/category/{{name}}",
        response_model=CategoryCustomizationOut,
    )
    def delete_category(
        name: str,
        _: None = Depends(require_auth),
        db: Session = Depends(get_db),
    ) -> CategoryCustomizationOut:
        """Delete a custom category and revert its rules / overrides."""
        if not customization.delete_custom_category(db, domain, name):
            raise HTTPException(status_code=404, detail="category not found")
        return _customization_state(db, domain)

    return router
