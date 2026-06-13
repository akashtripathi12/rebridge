"""Auth-dependency tests: private routes require a valid Cognito JWT (task 17.2).

These exercise :func:`rebridge_api.dependencies.get_current_user` end-to-end
through a FastAPI ``TestClient`` against a real
:class:`rebridge_api.auth.CognitoJwtVerifier`. Tokens are minted locally with a
generated RSA keypair and the matching public key is served as a fake JWKS, so
no Cognito / network access is involved.

Covers Requirements 16.1 (a valid Cognito JWT is required) and 16.2 (missing or
invalid tokens are rejected with 401): valid token accepted; missing token,
malformed header, bad signature, expired token, wrong audience, wrong issuer,
and unknown signing key all rejected with 401.
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
from rebridge_api.dependencies import CurrentUser, get_current_user, set_verifier

REGION = "us-east-1"
USER_POOL_ID = "us-east-1_testpool"
CLIENT_ID = "test-app-client-id"
ISSUER = f"https://cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}"
KID = "test-key-1"


# ---------------------------------------------------------------------------
# key / JWKS / token helpers
# ---------------------------------------------------------------------------


def _gen_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


SIGNING_KEY = _gen_key()
WRONG_KEY = _gen_key()


def _jwks_from(public_key, *, kid: str = KID) -> dict:
    jwk = json.loads(RSAAlgorithm.to_jwk(public_key))
    jwk.update({"kid": kid, "alg": "RS256", "use": "sig"})
    return {"keys": [jwk]}


JWKS = _jwks_from(SIGNING_KEY.public_key())


def _make_token(
    *,
    key: rsa.RSAPrivateKey = SIGNING_KEY,
    kid: str = KID,
    iss: str = ISSUER,
    aud: str | None = CLIENT_ID,
    client_id: str | None = None,
    exp_delta: int = 3600,
    sub: str = "user-1",
    alg: str = "RS256",
) -> str:
    now = int(time.time())
    payload: dict[str, object] = {"sub": sub, "iss": iss, "iat": now, "exp": now + exp_delta}
    if aud is not None:
        payload["aud"] = aud
    if client_id is not None:
        payload["client_id"] = client_id
    return jwt.encode(payload, key, algorithm=alg, headers={"kid": kid})


# ---------------------------------------------------------------------------
# app fixtures
# ---------------------------------------------------------------------------


def _build_app(verifier: CognitoJwtVerifier | None) -> FastAPI:
    app = FastAPI()
    if verifier is not None:
        set_verifier(app, verifier)

    @app.get("/private")
    def private(user: CurrentUser = Depends(get_current_user)) -> dict:
        return {"sub": user.subject}

    return app


@pytest.fixture
def verifier() -> CognitoJwtVerifier:
    return CognitoJwtVerifier(
        region=REGION,
        user_pool_id=USER_POOL_ID,
        app_client_id=CLIENT_ID,
        jwks_provider=static_jwks_provider(JWKS),
    )


@pytest.fixture
def client(verifier: CognitoJwtVerifier) -> TestClient:
    return TestClient(_build_app(verifier))


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# accept: a valid token (Req 16.1)
# ---------------------------------------------------------------------------


def test_valid_id_token_is_accepted(client):
    resp = client.get("/private", headers=_auth(_make_token()))
    assert resp.status_code == 200, resp.text
    assert resp.json()["sub"] == "user-1"


def test_valid_access_token_with_client_id_is_accepted(client):
    """Access tokens carry the app client id as `client_id`, not `aud`."""
    token = _make_token(aud=None, client_id=CLIENT_ID)
    resp = client.get("/private", headers=_auth(token))
    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# reject: missing / malformed credentials (Req 16.2)
# ---------------------------------------------------------------------------


def test_missing_authorization_header_is_401(client):
    resp = client.get("/private")
    assert resp.status_code == 401


def test_non_bearer_authorization_is_401(client):
    resp = client.get("/private", headers={"Authorization": _make_token()})
    assert resp.status_code == 401


def test_empty_bearer_token_is_401(client):
    resp = client.get("/private", headers={"Authorization": "Bearer "})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# reject: invalid tokens (Req 16.2)
# ---------------------------------------------------------------------------


def test_bad_signature_is_401(client):
    """Signed with a different key than the one published in the JWKS."""
    token = _make_token(key=WRONG_KEY)
    resp = client.get("/private", headers=_auth(token))
    assert resp.status_code == 401


def test_expired_token_is_401(client):
    token = _make_token(exp_delta=-10)
    resp = client.get("/private", headers=_auth(token))
    assert resp.status_code == 401


def test_wrong_audience_is_401(client):
    token = _make_token(aud="some-other-client")
    resp = client.get("/private", headers=_auth(token))
    assert resp.status_code == 401


def test_wrong_issuer_is_401(client):
    token = _make_token(iss="https://cognito-idp.us-east-1.amazonaws.com/us-east-1_evil")
    resp = client.get("/private", headers=_auth(token))
    assert resp.status_code == 401


def test_unknown_kid_is_401(client):
    """Token header references a signing key not present in the JWKS."""
    token = _make_token(kid="not-a-known-kid")
    resp = client.get("/private", headers=_auth(token))
    assert resp.status_code == 401


def test_garbage_token_is_401(client):
    resp = client.get("/private", headers=_auth("not.a.jwt"))
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# reject: app misconfigured with no verifier -> fail closed (Req 16.1)
# ---------------------------------------------------------------------------


def test_no_verifier_configured_fails_closed_401():
    app = _build_app(verifier=None)
    resp = TestClient(app).get("/private", headers=_auth(_make_token()))
    assert resp.status_code == 401
