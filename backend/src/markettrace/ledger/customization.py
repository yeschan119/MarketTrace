"""Shared category-customization layer for the card and passbook ledgers.

Both ledgers parse a statement and re-derive every entry's category from its
text on each read, using a fixed built-in rule table. This module adds a
persistent, user-controlled layer on top of that, with three precedence tiers:

1. **Per-entry override** — pins one transaction (by its stable ``entry_key``)
   to a category, regardless of what any rule says.
2. **Keyword rule** — maps a substring (merchant / 적요·내용) to a category and
   beats the built-in rules, applying to every matching transaction across all
   stored months and future statements.
3. **Built-in rule** — the existing hard-coded categorization (the ``base``).

A :class:`CategoryResolver` snapshots tiers 1–2 for one domain so the storage
layer can categorize a whole window of entries with a single DB read.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from markettrace.db.models import (
    LedgerCategoryRule,
    LedgerCustomCategory,
    LedgerEntryOverride,
)

CARD_DOMAIN = "card"
PASSBOOK_DOMAIN = "passbook"
_DOMAINS = (CARD_DOMAIN, PASSBOOK_DOMAIN)

_NORMALIZE_RE = re.compile(r"[\s._·•()/\\-]+")


class CustomizationError(Exception):
    """A category-customization request was invalid."""


def normalize_category_text(value: str) -> str:
    """Upper-case and strip separators so keyword matching is punctuation-blind."""
    return _NORMALIZE_RE.sub("", (value or "").upper())


def validate_domain(domain: str) -> str:
    if domain not in _DOMAINS:
        raise CustomizationError(f"unknown ledger domain: {domain}")
    return domain


# --- built-in category catalogs ------------------------------------------------

def _card_builtin_categories() -> list[str]:
    from markettrace.ledger.statements import _CATEGORY_RULES

    names = [category for category, _ in _CATEGORY_RULES]
    return [*names, "기타", "인식불가"]


def _passbook_builtin_categories() -> list[str]:
    from markettrace.passbook.statements import (
        _DESCRIPTION_CATEGORY_RULES,
        _SUMMARY_CATEGORY_RULES,
    )

    names = [category for category, _ in _SUMMARY_CATEGORY_RULES]
    names += [category for category, _ in _DESCRIPTION_CATEGORY_RULES]
    return [*names, "기타"]


def builtin_categories(domain: str) -> list[str]:
    """Return the named built-in category buckets for a domain (de-duplicated)."""
    validate_domain(domain)
    raw = (
        _card_builtin_categories()
        if domain == CARD_DOMAIN
        else _passbook_builtin_categories()
    )
    return _dedupe(raw)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


# --- resolver ------------------------------------------------------------------

@dataclass(frozen=True)
class CategoryResolver:
    """A snapshot of the override + rule layers for one domain."""

    overrides: dict[str, str]
    rules: tuple[tuple[str, str], ...]  # (keyword_norm, category), longest first

    def category_for(self, *, entry_key: str, text: str, base_category: str) -> str:
        """Resolve the effective category for one entry."""
        override = self.overrides.get(entry_key)
        if override is not None:
            return override
        if self.rules:
            normalized = normalize_category_text(text)
            for keyword_norm, category in self.rules:
                if keyword_norm and keyword_norm in normalized:
                    return category
        return base_category


def load_resolver(session: Session, domain: str) -> CategoryResolver:
    """Read a domain's overrides and rules into an in-memory resolver."""
    validate_domain(domain)
    overrides = {
        row.entry_key: row.category
        for row in session.scalars(
            select(LedgerEntryOverride).where(LedgerEntryOverride.domain == domain)
        )
    }
    rules = sorted(
        (
            (row.keyword_norm, row.category)
            for row in session.scalars(
                select(LedgerCategoryRule).where(LedgerCategoryRule.domain == domain)
            )
        ),
        key=lambda item: (-len(item[0]), item[0]),
    )
    return CategoryResolver(overrides=overrides, rules=tuple(rules))


# --- overrides -----------------------------------------------------------------

def list_overrides(session: Session, domain: str) -> list[LedgerEntryOverride]:
    validate_domain(domain)
    return list(
        session.scalars(
            select(LedgerEntryOverride)
            .where(LedgerEntryOverride.domain == domain)
            .order_by(LedgerEntryOverride.updated_at.desc())
        )
    )


def set_override(
    session: Session,
    domain: str,
    *,
    entry_key: str,
    category: str,
    description: str | None = None,
    now: datetime | None = None,
) -> LedgerEntryOverride:
    """Create or update the override for one transaction."""
    validate_domain(domain)
    category = _require_nonempty(category, "category")
    entry_key = _require_nonempty(entry_key, "entry_key")
    timestamp = now or datetime.now(tz=UTC)
    row = session.scalar(
        select(LedgerEntryOverride).where(
            LedgerEntryOverride.domain == domain,
            LedgerEntryOverride.entry_key == entry_key,
        )
    )
    if row is None:
        row = LedgerEntryOverride(
            domain=domain,
            entry_key=entry_key,
            created_at=timestamp,
        )
        session.add(row)
    row.category = category
    if description is not None:
        row.description = description
    row.updated_at = timestamp
    session.commit()
    session.refresh(row)
    return row


def clear_override(session: Session, domain: str, entry_key: str) -> bool:
    """Remove an override so the entry reverts to rule-based categorization."""
    validate_domain(domain)
    result = session.execute(
        delete(LedgerEntryOverride).where(
            LedgerEntryOverride.domain == domain,
            LedgerEntryOverride.entry_key == entry_key,
        )
    )
    session.commit()
    return bool(result.rowcount)


# --- keyword rules -------------------------------------------------------------

def list_rules(session: Session, domain: str) -> list[LedgerCategoryRule]:
    validate_domain(domain)
    return list(
        session.scalars(
            select(LedgerCategoryRule)
            .where(LedgerCategoryRule.domain == domain)
            .order_by(LedgerCategoryRule.created_at.desc())
        )
    )


def create_rule(
    session: Session,
    domain: str,
    *,
    keyword: str,
    category: str,
    now: datetime | None = None,
) -> LedgerCategoryRule:
    """Create or update a keyword→category rule (upsert on the normalized key)."""
    validate_domain(domain)
    keyword = _require_nonempty(keyword, "keyword")
    category = _require_nonempty(category, "category")
    keyword_norm = normalize_category_text(keyword)
    if not keyword_norm:
        raise CustomizationError("keyword has no matchable characters")
    row = session.scalar(
        select(LedgerCategoryRule).where(
            LedgerCategoryRule.domain == domain,
            LedgerCategoryRule.keyword_norm == keyword_norm,
        )
    )
    if row is None:
        row = LedgerCategoryRule(
            domain=domain,
            keyword_norm=keyword_norm,
            created_at=now or datetime.now(tz=UTC),
        )
        session.add(row)
    row.keyword = keyword
    row.category = category
    session.commit()
    session.refresh(row)
    return row


def delete_rule(session: Session, domain: str, rule_id: int) -> bool:
    validate_domain(domain)
    result = session.execute(
        delete(LedgerCategoryRule).where(
            LedgerCategoryRule.domain == domain,
            LedgerCategoryRule.id == rule_id,
        )
    )
    session.commit()
    return bool(result.rowcount)


# --- custom categories ---------------------------------------------------------

def list_custom_categories(session: Session, domain: str) -> list[LedgerCustomCategory]:
    validate_domain(domain)
    return list(
        session.scalars(
            select(LedgerCustomCategory)
            .where(LedgerCustomCategory.domain == domain)
            .order_by(LedgerCustomCategory.name)
        )
    )


def create_custom_category(
    session: Session, domain: str, *, name: str, now: datetime | None = None
) -> LedgerCustomCategory:
    validate_domain(domain)
    name = _require_nonempty(name, "name")
    if name in builtin_categories(domain):
        raise CustomizationError("category already exists as a built-in category")
    row = session.scalar(
        select(LedgerCustomCategory).where(
            LedgerCustomCategory.domain == domain,
            LedgerCustomCategory.name == name,
        )
    )
    if row is not None:
        return row
    row = LedgerCustomCategory(
        domain=domain, name=name, created_at=now or datetime.now(tz=UTC)
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def delete_custom_category(session: Session, domain: str, name: str) -> bool:
    """Delete a custom category and any rules / overrides that point to it.

    Overrides and rules that referenced the removed category are dropped so the
    affected transactions revert to built-in categorization.
    """
    validate_domain(domain)
    # A category can exist only via a rule or override (no row in the custom
    # table), so count deletions across all three to report success correctly.
    affected = 0
    affected += session.execute(
        delete(LedgerCustomCategory).where(
            LedgerCustomCategory.domain == domain,
            LedgerCustomCategory.name == name,
        )
    ).rowcount
    affected += session.execute(
        delete(LedgerCategoryRule).where(
            LedgerCategoryRule.domain == domain,
            LedgerCategoryRule.category == name,
        )
    ).rowcount
    affected += session.execute(
        delete(LedgerEntryOverride).where(
            LedgerEntryOverride.domain == domain,
            LedgerEntryOverride.category == name,
        )
    ).rowcount
    session.commit()
    return affected > 0


@dataclass(frozen=True)
class AvailableCategory:
    name: str
    source: str  # "builtin" | "custom"


def available_categories(session: Session, domain: str) -> list[AvailableCategory]:
    """Return every category a user can assign: built-ins plus custom ones.

    Custom names include explicitly created categories and any category already
    referenced by a rule or override, so nothing a user picked can disappear
    from the list.
    """
    validate_domain(domain)
    builtins = builtin_categories(domain)
    builtin_set = set(builtins)
    custom: list[str] = [row.name for row in list_custom_categories(session, domain)]
    custom += [row.category for row in list_rules(session, domain)]
    custom += [row.category for row in list_overrides(session, domain)]
    ordered = [AvailableCategory(name=name, source="builtin") for name in builtins]
    ordered += [
        AvailableCategory(name=name, source="custom")
        for name in _dedupe(custom)
        if name not in builtin_set
    ]
    return ordered


def _require_nonempty(value: str, field: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise CustomizationError(f"{field} must not be empty")
    return cleaned
