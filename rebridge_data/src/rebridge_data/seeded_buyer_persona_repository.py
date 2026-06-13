"""Seeded :class:`BuyerPersonaRepository` implementation (Req 13.6, 18.2).

In v1 the seeded buyer-persona dataset is the *only* demand source: the
Demand_Matching_Engine retrieves its candidate buyers exclusively through this
repository (Requirements 13.6, 18.2). The persona data is synthetic placeholder
data shipped as package data (``data/buyer_personas.json``) and carries no PII;
the seam is ready to be swapped for a live buyer-data source later without
touching the service layer.

Unlike its boto3-backed siblings in this package, this implementation is pure
data — it loads a JSON seed from package resources (or an explicit, injected
persona list) and answers :meth:`candidates` from memory. No AWS clients are
constructed and ``boto3`` is not imported here.

``candidates(geo, category)`` returns the seeded personas that both:

* fall within the queried neighborhood — their ``geohash5`` begins with the
  ``geo`` prefix (a 5-char geohash matches itself; a shorter prefix widens the
  neighborhood); and
* carry a wishlist/cart signal for ``category`` — ``category`` appears in their
  ``category_interests``.

Matching is case-insensitive on ``category`` and the geohash prefix so callers
do not have to normalize before querying.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from importlib import resources
from typing import Any

from rebridge_data.interfaces import BuyerPersonaRepository
from rebridge_data.models import BuyerPersona

__all__ = ["SeededBuyerPersonaRepository"]


class SeededBuyerPersonaRepository(BuyerPersonaRepository):
    """In-memory repository over a synthetic seeded buyer-persona dataset.

    By default the placeholder seed shipped as package data
    (``data/buyer_personas.json``) is loaded. Pass ``personas`` to inject an
    explicit list of :class:`~rebridge_data.models.BuyerPersona` objects (used
    by tests and by any later live-data adapter), bypassing the packaged seed
    entirely.
    """

    _PACKAGE = "rebridge_data"
    _RESOURCE = "data/buyer_personas.json"

    def __init__(self, personas: Iterable[BuyerPersona] | None = None) -> None:
        if personas is not None:
            self._personas: list[BuyerPersona] = list(personas)
        else:
            self._personas = _load_packaged_personas(self._PACKAGE, self._RESOURCE)

    @property
    def personas(self) -> list[BuyerPersona]:
        """A copy of the full seeded persona pool (order preserved)."""

        return list(self._personas)

    # -- BuyerPersonaRepository ----------------------------------------------

    def candidates(self, geo: str, category: str) -> list[BuyerPersona]:
        """Return seeded buyers in the ``geo`` neighborhood interested in ``category``.

        A persona is a candidate when its ``geohash5`` starts with the ``geo``
        prefix and ``category`` is one of its ``category_interests``. Both the
        geohash prefix and the category comparison are case-insensitive. Input
        order from the seed is preserved in the result.
        """

        geo_prefix = geo.strip().lower()
        wanted = category.strip().lower()
        return [
            persona
            for persona in self._personas
            if persona.geohash5.lower().startswith(geo_prefix)
            and wanted in {c.lower() for c in persona.category_interests}
        ]


def _load_packaged_personas(package: str, resource: str) -> list[BuyerPersona]:
    """Load and parse the packaged JSON persona seed."""
    ref = resources.files(package).joinpath(resource)
    text = ref.read_text(encoding="utf-8")
    raw = json.loads(text)
    return _personas_from_payload(raw)


def _personas_from_payload(raw: Any) -> list[BuyerPersona]:
    """Parse the seed payload into persona records.

    Accepts either a bare JSON array of persona objects or an object with a
    ``personas`` array (the seed file also carries a documentary ``_note``).
    """
    if isinstance(raw, Mapping):
        rows = raw.get("personas", [])
    else:
        rows = raw
    if not isinstance(rows, list):
        raise ValueError("buyer-persona seed must be a list or {'personas': [...]}")
    return [_row_to_persona(row) for row in rows]


def _row_to_persona(row: Mapping[str, Any]) -> BuyerPersona:
    try:
        return BuyerPersona(
            buyer_id=str(row["buyer_id"]),
            geohash5=str(row["geohash5"]),
            persona_type=str(row["persona_type"]),
            category_interests=list(row.get("category_interests", [])),
            intent=float(row.get("intent", 0.0)),
            lifecycle=float(row.get("lifecycle", 0.0)),
            price_sensitivity=float(row.get("price_sensitivity", 0.0)),
        )
    except KeyError as exc:
        raise ValueError(f"buyer-persona row missing field: {exc}") from exc
