"""Baseline UWG category tree lookup (docs/extensions.md, section 7).

The JSON file is a flat {category_id: name} snapshot generated from
docs/fega_categories.md's crawl (2026-08-10). It's a baseline for ID
validation/normalization, not a live source - FEGA can rename/move
categories without this package being updated.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources


@lru_cache(maxsize=1)
def _category_names() -> dict[str, str]:
    data = resources.files(__package__).joinpath("data/categories.json").read_text(encoding="utf-8")
    return json.loads(data)


def category_name(category_id: str) -> str | None:
    """Look up a category's name in the baseline. None if unknown."""
    return _category_names().get(category_id)


def normalize_category_id(category_id: str) -> str:
    """Map a Warengruppe ID from an article detail page onto a baseline tree ID.

    Detail pages sometimes link to an ID with one extra trailing segment
    compared to the tree extracted via cmd=Hierarchie (e.g. "UWG_14_87_0" on
    the page vs. "UWG_14_87" in the tree) - see docs/extensions.md, section
    2.5. Strategy: try the exact ID first, then strip the last "_<digits>"
    segment once and try again. Falls back to the original ID unchanged if
    neither matches (still useful as an opaque identifier, just not
    resolvable to a name via this baseline).
    """
    names = _category_names()
    if category_id in names:
        return category_id
    stripped = category_id.rsplit("_", 1)[0]
    if stripped in names:
        return stripped
    return category_id
