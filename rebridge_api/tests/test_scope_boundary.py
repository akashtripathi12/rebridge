"""V1 scope-boundary smoke tests (Requirement 18.1-18.4).

These are deliberately lightweight, *structural* smoke tests that assert the v1
scope discipline of design.md ("v1 Scope Boundaries") and Requirement 18 holds
across the production source of all three packages:

* **18.1** the grading -> Health Card -> routing slice is the operational core and
  the roadmap-only capabilities (fraud-detection ML, donation logistics) are
  absent;
* **18.2** the *seeded* buyer-persona repository is the only demand source -- the
  composition root wires :class:`SeededBuyerPersonaRepository` and there is no
  live/external buyer-data source;
* **18.3** Pillar 5 prevention is represented by the data-capture shape only --
  there is no prevention-model *execution* module or symbol;
* **18.4** live payment processing is absent -- ``POST /listings/{id}/buy`` is a
  simulated checkout that emits SOLD and touches no payment gateway.

Rather than asserting on brittle exact names, the absence checks scan the
*production* source (the installed ``src`` package directories, never the test
suites) and inspect **code identifiers only** via the AST -- module/class/function
names, imported names, and referenced attributes. Docstrings and comments are
ignored on purpose: the codebase legitimately *mentions* "payment", "fraud", and
"donation" in negative/explanatory prose ("no payment is processed",
"out of scope"), and a naive text search would flag those. A forbidden *concern*
is only considered present if it appears as a real code symbol (an import, a
definition, or a call), which is what "building" the capability would require.
"""

from __future__ import annotations

import ast
from pathlib import Path

import rebridge_api
import rebridge_api.routers.listings  # ensure the buy-route module is importable
import rebridge_data
import rebridge_service
from rebridge_data.interfaces import BuyerPersonaRepository
from rebridge_data.seeded_buyer_persona_repository import SeededBuyerPersonaRepository

# Importing the wiring module ensures the composition root (and therefore every
# concrete it constructs) is loaded before we introspect subclasses/sources.
from rebridge_api import wiring


# ---------------------------------------------------------------------------
# Source-scanning helpers (production packages only; identifiers, not prose)
# ---------------------------------------------------------------------------

# The installed package directories are the production source roots. Their
# parent test suites live outside these dirs, so scanning here never trips over
# the tests' own fakes or this module's forbidden-token vocabulary.
PRODUCTION_PACKAGE_DIRS: tuple[Path, ...] = tuple(
    Path(module.__file__).resolve().parent
    for module in (rebridge_api, rebridge_data, rebridge_service)
)


def _python_sources() -> list[Path]:
    """Every ``.py`` file under the three production package source roots."""
    files: list[Path] = []
    for root in PRODUCTION_PACKAGE_DIRS:
        files.extend(
            p
            for p in root.rglob("*.py")
            if "__pycache__" not in p.parts
        )
    return files


def _code_identifiers(tree: ast.AST) -> set[str]:
    """Collect identifiers that represent *code*, excluding strings/comments.

    Returns the lowercased set of: defined module/class/function names, imported
    module and symbol names (and aliases), referenced names, and accessed
    attribute names. String constants (docstrings, messages) and comments are
    not part of the AST node set we inspect, so explanatory prose mentioning an
    excluded concern is never counted as that concern being built.
    """

    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
                if alias.asname:
                    names.add(alias.asname)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module)
            for alias in node.names:
                names.add(alias.name)
                if alias.asname:
                    names.add(alias.asname)
    return {n.lower() for n in names}


def _find_concern(forbidden_tokens: set[str]) -> list[tuple[str, str, str]]:
    """Return ``(file, identifier, token)`` hits for any forbidden token.

    A hit is recorded when a forbidden token appears as a substring of a code
    identifier (module path, class/def name, import, or attribute) OR of a
    source file's stem. Scans production source only.
    """

    hits: list[tuple[str, str, str]] = []
    for path in _python_sources():
        # A module *named* for a forbidden concern is itself a violation.
        stem = path.stem.lower()
        for token in forbidden_tokens:
            if token in stem:
                hits.append((str(path), f"<module:{path.stem}>", token))

        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for identifier in _code_identifiers(tree):
            for token in forbidden_tokens:
                if token in identifier:
                    hits.append((str(path), identifier, token))
    return hits


# Forbidden code vocabulary per excluded concern. Chosen to be specific enough
# that no legitimate identifier in this codebase contains them as a substring
# (verified: the words "payment"/"fraud"/"donation"/"prevention" appear only in
# docstrings/messages, which this scan ignores).
PAYMENT_TOKENS = {"stripe", "paypal", "braintree", "payment", "checkout_session"}
FRAUD_ML_TOKENS = {
    "fraud",
    "sklearn",
    "tensorflow",
    "xgboost",
    "lightgbm",
    "keras",
    "torch",
}
DONATION_LOGISTICS_TOKENS = {
    "donation_logistics",
    "donationlogistics",
    "donation_pickup",
    "donationpickup",
    "pickup_schedul",
    "schedule_pickup",
    "charity_dispatch",
    "donation_fulfillment",
}
PREVENTION_TOKENS = {"prevention", "preventionmodel"}


# ---------------------------------------------------------------------------
# 18.2 -- the seeded buyer-persona repository is the only demand source
# ---------------------------------------------------------------------------


def _all_subclasses(cls: type) -> set[type]:
    found: set[type] = set()
    for sub in cls.__subclasses__():
        found.add(sub)
        found |= _all_subclasses(sub)
    return found


def test_seeded_repository_is_the_only_buyer_persona_concrete():
    """Req 18.2 / 13.6: the seeded repo is the sole BuyerPersonaRepository concrete.

    Across the loaded production packages, ``SeededBuyerPersonaRepository`` is the
    only concrete implementation of the ``BuyerPersonaRepository`` demand seam.
    Subclasses defined under a test suite (none today) are ignored so the
    assertion stays about the shipped system.
    """

    production_concretes = {
        sub
        for sub in _all_subclasses(BuyerPersonaRepository)
        if "test" not in sub.__module__.split(".")
    }
    assert production_concretes == {SeededBuyerPersonaRepository}


def test_composition_root_wires_seeded_demand_source_only():
    """Req 18.2: the composition root injects the seeded repo as the demand source.

    Building the services (offline; boto3 gateways are constructed, never called)
    must wire the Demand_Matching_Engine to a ``SeededBuyerPersonaRepository`` and
    nothing else. Accessing the engine's private ``_buyers`` seam keeps the check
    direct without needing a live AWS environment.
    """

    from moto import mock_aws

    with mock_aws():
        built = wiring.build_services(wiring.Settings.from_env({}))

    assert isinstance(built.demand_engine._buyers, SeededBuyerPersonaRepository)


def test_wiring_source_constructs_only_the_seeded_demand_source():
    """Req 18.2: ``wiring.py`` constructs the seeded repo and no other demand source.

    Inspect the composition root's AST for the classes it instantiates. The only
    buyer/demand source it may construct is ``SeededBuyerPersonaRepository``; any
    other ``*Buyer*Repository``/``*Persona*`` construction would signal a live or
    alternate demand source creeping into v1.
    """

    wiring_path = Path(wiring.__file__).resolve()
    tree = ast.parse(wiring_path.read_text(encoding="utf-8"), filename=str(wiring_path))

    constructed: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                constructed.add(func.id)
            elif isinstance(func, ast.Attribute):
                constructed.add(func.attr)

    assert "SeededBuyerPersonaRepository" in constructed

    # A demand *data source* is a BuyerPersonaRepository concrete. Flag only
    # PascalCase constructions that look like a persona/buyer *repository*, so
    # an alternate or live demand source is caught -- but the demand-matching
    # side-effect gateways (EventBridgeBuyerNotifier / EventBridgeSecondChanceShelf),
    # which consume rather than source buyer data, are correctly ignored.
    demand_like = {
        name
        for name in constructed
        if name[:1].isupper()
        and (
            "persona" in name.lower()
            or ("buyer" in name.lower() and "repositor" in name.lower())
        )
        and name != "SeededBuyerPersonaRepository"
    }
    assert demand_like == set(), f"unexpected demand source(s) constructed: {demand_like}"


# ---------------------------------------------------------------------------
# 18.3 -- prevention is the data-capture shape only (no model execution)
# ---------------------------------------------------------------------------


def test_no_prevention_model_execution_symbol():
    """Req 18.3: Pillar 5 prevention is data-capture shape only, not executed.

    There must be no prevention-model *execution* surface in production code: no
    module named for prevention and no class/function/import carrying a
    prevention identifier. The data-capture *shape* (event/lake schema) is design
    only and introduces no such executable symbol.
    """

    hits = _find_concern(PREVENTION_TOKENS)
    assert hits == [], f"prevention-model execution symbol(s) present: {hits}"


# ---------------------------------------------------------------------------
# 18.4 -- live payment processing is absent; buy is a simulated checkout
# ---------------------------------------------------------------------------


def test_no_payment_gateway_anywhere_in_production_source():
    """Req 18.4: no live payment gateway is imported, defined, or called."""

    hits = _find_concern(PAYMENT_TOKENS)
    assert hits == [], f"live payment symbol(s) present: {hits}"


def test_buy_route_emits_sold_without_touching_a_payment_gateway():
    """Req 18.4: the buy handler emits SOLD and calls no payment gateway.

    Statically inspect the ``buy_listing`` handler: it must update the item to
    SOLD and emit a SOLD event, and the attributes/names it references must not
    include any payment-gateway token.
    """

    listings_path = Path(rebridge_api.routers.listings.__file__).resolve()
    tree = ast.parse(listings_path.read_text(encoding="utf-8"), filename=str(listings_path))

    buy_fn = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "buy_listing"
        ),
        None,
    )
    assert buy_fn is not None, "buy_listing handler not found"

    referenced = _code_identifiers(buy_fn)
    assert "emit_sold" in referenced
    assert "update_status" in referenced

    payment_hits = {
        identifier
        for identifier in referenced
        for token in PAYMENT_TOKENS
        if token in identifier
    }
    assert payment_hits == set(), f"buy handler references payment symbol(s): {payment_hits}"


def test_buy_endpoint_is_simulated_and_emits_sold(client, harness):
    """Req 18.4: exercising the buy endpoint is a simulated, payment-free SOLD.

    Reuses the in-memory harness (no AWS): create + grade + list an item, then
    buy it. The response must be flagged ``simulated`` and the only side effects
    are the SOLD status transition and exactly one SOLD lifecycle event -- there
    is no payment artifact in the system.
    """

    from rebridge_data.models import GradeRecord

    # Create an item.
    create = client.post(
        "/items",
        json={"context_source": "manual", "category": "electronics", "age_months": 10},
    )
    assert create.status_code == 201, create.text
    item_id = create.json()["item_id"]

    # Seed a grade so the listing's grade-required guard passes, then list it.
    harness.item_repo.put_grade(
        item_id,
        GradeRecord(grade="Good", confidence=0.95, summary="seeded for buy smoke test"),
    )
    listing = client.post(
        "/listings",
        json={
            "item_id": item_id,
            "category": "electronics",
            "price": "120.00",
            "geohash5": "9q8yy",
        },
    )
    assert listing.status_code == 201, listing.text

    resp = client.post(f"/listings/{item_id}/buy")
    assert resp.status_code == 200
    body = resp.json()
    assert body["simulated"] is True
    assert body["status"] == "SOLD"

    # The only lifecycle effect is exactly one SOLD event for this item.
    sold = harness.publisher.events_of("SOLD")
    assert len(sold) == 1 and sold[0].item_id == item_id


# ---------------------------------------------------------------------------
# 18.1 -- v1 core holds: roadmap-only capabilities are absent
# ---------------------------------------------------------------------------


def test_no_fraud_detection_ml_in_production_source():
    """Req 18.1/18.4: fraud-detection ML (libraries or symbols) is absent."""

    hits = _find_concern(FRAUD_ML_TOKENS)
    assert hits == [], f"fraud-detection ML symbol(s) present: {hits}"


def test_no_donation_logistics_in_production_source():
    """Req 18.1/18.4: donation *logistics execution* is absent.

    The excluded concern is an operational subsystem that *fulfills* donations
    (scheduling pickups, dispatching to charities). The routing core legitimately
    includes a ``DONATE`` disposition decision and a ``logistics`` cost input
    (Requirement 10); those are in v1 scope and are intentionally not treated as
    donation-logistics execution, so the scan targets execution-specific symbols
    only.
    """

    hits = _find_concern(DONATION_LOGISTICS_TOKENS)
    assert hits == [], f"donation-logistics execution symbol(s) present: {hits}"


def test_v1_core_slice_modules_are_present():
    """Req 18.1: the grading -> Health Card -> routing core is operational.

    Sanity-check that the core slice the v1 scope commits to building is in fact
    present and importable: the grading engine/pipeline, the Product Health Card
    service, and the routing agent.
    """

    import rebridge_service.grading_engine  # noqa: F401
    import rebridge_service.grading_pipeline  # noqa: F401
    import rebridge_service.health_card_service  # noqa: F401
    import rebridge_service.routing_agent  # noqa: F401

    assert rebridge_service.health_card_service.HealthCardService is not None
    assert rebridge_service.routing_agent.RoutingAgent is not None
