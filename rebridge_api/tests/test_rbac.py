"""Role-based access control tests: operator routes require ``custom:role`` (RBAC).

Two layers of coverage:

* **Integration through the wired app** (the ``harness`` fixture): with the auth
  dependency overridden to a customer / operator / role-less principal, the
  back-office routes (item create, presign, grade, route, listing CRUD, review
  console) reject a non-operator with **403** while admitting an operator, and
  the customer-facing routes (marketplace browse, buyer matches, item/listing
  reads, simulated buy) admit any authenticated principal.
* **End-to-end through the real verifier**: a Cognito-style JWT carrying
  ``custom:role`` is decoded and the role is extracted and enforced, proving the
  gate reads the role from *verified* claims and not from anything client-supplied.

Enforcement lives entirely on the server (the ``require_role`` dependency), so it
holds regardless of what the frontend does.
"""

from __future__ import annotations

import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

from rebridge_api.auth import CognitoJwtVerifier, static_jwks_provider
from rebridge_api.dependencies import (
    CurrentUser,
    get_current_user,
    require_role,
    set_verifier,
)

from tests.conftest import Harness


# ---------------------------------------------------------------------------
# the route inventory under test
# ---------------------------------------------------------------------------
#
# Each entry is (method, path, json_body). Bodies are valid against the request
# schema so the only thing that can produce a 401/403 is the auth gate (not a
# 422 body-validation error). Path ids may be dummies: authorization is resolved
# before the handler runs, so an operator simply falls through to a 404/409.

_OPERATOR_ROUTES = [
    ("POST", "/items", {"context_source": "manual", "category": "electronics", "age_months": 8}),
    ("POST", "/items/itm_x/photos:presign", {"count": 3}),
    ("POST", "/items/itm_x/grade", {"photo_keys": ["a", "b"]}),
    ("POST", "/items/itm_x/route", {}),
    (
        "POST",
        "/listings",
        {"item_id": "itm_x", "category": "electronics", "price": "120.00", "geohash5": "9q8yy"},
    ),
    ("PUT", "/listings/itm_x", {"price": "99.50"}),
    ("DELETE", "/listings/itm_x", None),
    ("GET", "/review/queue", None),
    ("POST", "/review/itm_x", {"action": "CONFIRM"}),
]

_CUSTOMER_ROUTES = [
    ("GET", "/marketplace?category=electronics", None),
    ("GET", "/items/itm_x/matches", None),
    ("GET", "/items/itm_x", None),
    ("GET", "/listings/itm_x", None),
    ("POST", "/listings/itm_x/buy", None),
]


def _as_role(harness: Harness, role: str | None) -> None:
    """Override the wired auth dependency with a principal carrying ``role``."""

    harness.app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        subject="u-1", claims={"sub": "u-1"}, role=role
    )


def _call(client: TestClient, method: str, path: str, body):
    return client.request(method, path, json=body)


# ---------------------------------------------------------------------------
# integration: the operator gate on back-office routes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method,path,body", _OPERATOR_ROUTES)
def test_customer_is_forbidden_from_operator_routes(harness, method, path, body):
    """A logged-in customer hitting any operator route gets 403, not the result."""

    _as_role(harness, "customer")
    resp = _call(harness.client, method, path, body)
    assert resp.status_code == 403, f"{method} {path} -> {resp.status_code}: {resp.text}"


@pytest.mark.parametrize("method,path,body", _OPERATOR_ROUTES)
def test_roleless_user_is_forbidden_from_operator_routes(harness, method, path, body):
    """An authenticated token with no ``custom:role`` is treated as non-operator."""

    _as_role(harness, None)
    resp = _call(harness.client, method, path, body)
    assert resp.status_code == 403, f"{method} {path} -> {resp.status_code}: {resp.text}"


@pytest.mark.parametrize("method,path,body", _OPERATOR_ROUTES)
def test_operator_passes_the_gate_on_operator_routes(harness, method, path, body):
    """An operator clears the gate (the auth layer never answers 401/403)."""

    _as_role(harness, "operator")
    resp = _call(harness.client, method, path, body)
    assert resp.status_code not in (401, 403), (
        f"operator blocked on {method} {path} -> {resp.status_code}: {resp.text}"
    )


# ---------------------------------------------------------------------------
# integration: customer-facing routes admit any authenticated principal
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", ["customer", "operator", None])
@pytest.mark.parametrize("method,path,body", _CUSTOMER_ROUTES)
def test_customer_routes_admit_any_authenticated_user(harness, role, method, path, body):
    """Marketplace browse + buyer matches + reads are open to every logged-in user."""

    _as_role(harness, role)
    resp = _call(harness.client, method, path, body)
    assert resp.status_code != 403, (
        f"{role!r} wrongly blocked on {method} {path}: {resp.text}"
    )


# ---------------------------------------------------------------------------
# end-to-end: role is read from a *verified* custom:role claim
# ---------------------------------------------------------------------------

REGION = "us-east-1"
USER_POOL_ID = "us-east-1_rbacpool"
CLIENT_ID = "rbac-app-client"
ISSUER = f"https://cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}"
KID = "rbac-key-1"

_SIGNING_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwks() -> dict:
    jwk = json.loads(RSAAlgorithm.to_jwk(_SIGNING_KEY.public_key()))
    jwk.update({"kid": KID, "alg": "RS256", "use": "sig"})
    return {"keys": [jwk]}


def _token(*, role: str | None) -> str:
    now = int(time.time())
    payload: dict[str, object] = {
        "sub": "user-1",
        "iss": ISSUER,
        "aud": CLIENT_ID,
        "iat": now,
        "exp": now + 3600,
    }
    if role is not None:
        payload["custom:role"] = role
    return jwt.encode(payload, _SIGNING_KEY, algorithm="RS256", headers={"kid": KID})


@pytest.fixture
def operator_app() -> TestClient:
    app = FastAPI()
    set_verifier(
        app,
        CognitoJwtVerifier(
            region=REGION,
            user_pool_id=USER_POOL_ID,
            app_client_id=CLIENT_ID,
            jwks_provider=static_jwks_provider(_jwks()),
        ),
    )

    @app.get("/op")
    def op(user: CurrentUser = Depends(require_role("operator"))) -> dict:
        return {"sub": user.subject, "role": user.role}

    return TestClient(app)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_operator_token_clears_real_verifier_gate(operator_app):
    resp = operator_app.get("/op", headers=_auth(_token(role="operator")))
    assert resp.status_code == 200, resp.text
    assert resp.json()["role"] == "operator"


def test_customer_token_is_forbidden_through_real_verifier(operator_app):
    resp = operator_app.get("/op", headers=_auth(_token(role="customer")))
    assert resp.status_code == 403


def test_roleless_token_is_forbidden_through_real_verifier(operator_app):
    resp = operator_app.get("/op", headers=_auth(_token(role=None)))
    assert resp.status_code == 403


def test_missing_token_is_unauthorized_not_forbidden(operator_app):
    """No token is still a 401 (authn) — the role gate only runs after authn."""

    resp = operator_app.get("/op")
    assert resp.status_code == 401


def test_role_claim_is_normalized(operator_app):
    """Cognito values are matched case/space-insensitively ('Operator ' -> operator)."""

    resp = operator_app.get("/op", headers=_auth(_token(role="  Operator ")))
    assert resp.status_code == 200, resp.text
    assert resp.json()["role"] == "operator"
