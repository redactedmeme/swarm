"""_short_desc has to handle both character-file schemas.

The newer one (RedactedDegen and 4 others) nests the bio under `core_identity`,
so `swarm roster` rendered those agents with a blank description.
"""
from __future__ import annotations

from swarm_core.agent_registry import _short_desc


def test_flat_schema_still_wins():
    assert _short_desc({"description": "flat one", "core_identity": {"bio": "nested"}}) == "flat one"


def test_core_identity_bio():
    assert _short_desc({"core_identity": {"bio": "Former Degenerate Spartan."}}) == "Former Degenerate Spartan."


def test_core_identity_philosophy_is_the_fallback():
    assert _short_desc({"core_identity": {"philosophy": "only numbers and edges"}}) == "only numbers and edges"


def test_swarm_role_before_persona():
    assert _short_desc({"swarm_role": "LP scout", "persona": {"role": "other"}}) == "LP scout"


def test_persona_dict_still_works():
    assert _short_desc({"persona": {"role": "governance architect"}}) == "governance architect"


def test_clamped_to_80_chars():
    assert len(_short_desc({"core_identity": {"bio": "x" * 300}})) == 80


def test_empty_dict_is_empty_string():
    assert _short_desc({}) == ""
