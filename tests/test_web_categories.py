"""Tests for the UWG category baseline lookup (docs/extensions.md, section 7)."""

from __future__ import annotations

from fega_schmitt_client.web._categories import category_name, normalize_category_id


def test_normalize_category_id_returns_exact_match_unchanged():
    assert normalize_category_id("UWG_1_1") == "UWG_1_1"


def test_normalize_category_id_strips_unknown_trailing_segment():
    # "UWG_1_1_0" doesn't exist in the baseline tree, but "UWG_1_1" does -
    # see docs/extensions.md, section 2.5, for the suffix quirk this handles.
    assert normalize_category_id("UWG_1_1_0") == "UWG_1_1"


def test_normalize_category_id_falls_back_to_original_when_unresolvable():
    assert normalize_category_id("UWG_does_not_exist") == "UWG_does_not_exist"


def test_category_name_resolves_known_id():
    assert category_name("UWG_1_1") == "Aderendhülsen"


def test_category_name_returns_none_for_unknown_id():
    assert category_name("UWG_does_not_exist") is None
