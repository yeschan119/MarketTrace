"""Tests for the canonical event-type taxonomy used by the eval harness."""

from __future__ import annotations

import pytest

from markettrace.eval.goldset import load_goldset
from markettrace.eval.taxonomy import CANONICAL_FAMILIES, OTHER, canonicalize


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # earnings family — the fragmented synonyms all collapse together
        ("earnings_release", "earnings"),
        ("earnings_beat", "earnings"),
        ("earnings_conference_call", "earnings"),  # 'conference' must NOT win
        ("sales_report", "earnings"),
        # guidance is split out from earnings
        ("earnings_guidance", "guidance"),
        ("earnings_guide", "guidance"),
        ("guidance_update", "guidance"),
        # insider vs ownership disambiguation
        ("insider_trading_report", "insider_trading"),
        ("insider_sale", "insider_trading"),
        ("internal_transaction", "insider_trading"),
        ("trading_plan", "insider_trading"),
        ("ownership_change", "ownership_change"),
        ("shareholding_change", "ownership_change"),
        ("ownership_structure_disclosure", "ownership_change"),
        # buyback beats the generic stock_acquisition -> merger rule
        ("treasury_stock_acquisition", "buyback"),
        ("share_buyback_announcement", "buyback"),
        ("stock_acquisition", "merger_acquisition"),
        ("merger_announcement", "merger_acquisition"),
        # capital raise
        ("debt_offering", "capital_raise"),
        ("bond_issuance", "capital_raise"),
        ("capital_increase", "capital_raise"),
        ("preferred_stock_issuance", "capital_raise"),
        # governance
        ("board_appointment", "governance"),
        ("executive_departure", "governance"),
        ("management_change", "governance"),
        ("compensation_award", "governance"),
        # meetings vs IR
        ("annual_meeting", "shareholder_meeting"),
        ("shareholder_meeting_result", "shareholder_meeting"),
        ("investor_conference", "ir_event"),
        ("conference_announcement", "ir_event"),
        # others
        ("regulatory_action", "regulatory"),
        ("lawsuit", "regulatory"),
        # Reg FD is a disclosure vehicle, not an enforcement action -> other
        ("regulation_fd_disclosure", OTHER),
        ("dividend_declaration", "dividend"),
        ("sustainability_report_release", "esg_report"),
        ("contract_award", "contract_partnership"),
        ("investment_plan_announcement", "investment"),
        ("macro_data_release", "macro"),
        ("product_launch", "product"),
        # genuinely vague -> other
        ("corporate_disclosure", OTHER),
        ("company_update", OTHER),
        ("related_party_transaction", OTHER),
        ("financial_transaction", OTHER),
    ],
)
def test_canonicalize_cases(raw: str, expected: str) -> None:
    assert canonicalize(raw) == expected


def test_canonicalize_is_case_and_whitespace_insensitive() -> None:
    assert canonicalize("  Insider_Trading_Report  ") == "insider_trading"


def test_canonicalize_idempotent_on_families() -> None:
    # Every canonical family name maps to itself (needed so a canonically
    # labelled gold set is scored consistently).
    for family in CANONICAL_FAMILIES:
        assert canonicalize(family) == family


def test_every_family_is_in_the_family_set() -> None:
    assert OTHER in CANONICAL_FAMILIES
    # Spot check a representative subset is present.
    for fam in ("earnings", "insider_trading", "governance", "capital_raise", "macro"):
        assert fam in CANONICAL_FAMILIES


def test_seed_goldset_labels_are_canonical_families() -> None:
    # Every gold label in the shipped seed set must be a valid canonical family
    # (self-canonicalising) so the harness scores it at the family level.
    for ex in load_goldset():
        assert ex.gold_event_type in CANONICAL_FAMILIES, ex.id
        assert canonicalize(ex.gold_event_type) == ex.gold_event_type, ex.id
