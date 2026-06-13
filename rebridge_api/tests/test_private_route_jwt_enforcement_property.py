"""Property-based test for private-route JWT enforcement.

# Feature: rebridge-backend, Property 28: Private routes require a valid JWT

Property 28 (design.md): *For any* private route, a request with a missing or
invalid JWT SHALL be rejected with an unauthorized error.

**Validates: Requirements 16.1, 16.2**

The test drives requests through a FastAPI ``TestClient`` against a real
:class:`rebridge_api.auth.CognitoJwtVerifier`. A single RSA keypair is generated
once at import time and its public half is served as a fake JWKS (via
:func:`static_jwks_provider`), so tokens are minted locally and no Cognito /
network access is involved. Signing reuses that one key; only the *claims*
(and, for the negative direction, the way the credential is mangled) vary per
example, which keeps generation fast.

Two universal properties are asserted:

* **Negative (Req 16.2).** For arbitrarily malformed or invalid credentials --
  random strings, tokens signed by the wrong key, expired tokens, tokens with
  the wrong audience or issuer, tokens referencing an unknown signing key, and
  missing / garbled ``Authorization`` headers -- the private route responds 401.
* **Positive (Req 16.1).** For validly minted tokens (varied ``sub`` and expiry
  within the validity window, presented as either an id-token via ``aud`` or an
  access-token via ``client_id``), the private route does *not* respond 401 --
  it returns 200.
"""

from __future__ import annotations

import json
import string
import time

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st
from jwt.algorithms import RSAAlgorithm

from rebridge_api.auth import CognitoJwtVerifier, static_jwks_provider
from rebridge_api.dependencies import CurrentUser, get_current_user, set_verifier

# Minimum property iterations required by the task.
_ITERATIONS = 150

REGION = "us-east-1"
USER_POOL_ID = "us-east-1_testpool"
CLIENT_ID = "test-app-client-id"
ISSUER = f"https://cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}"
KID = "test-key-1"


# ---------------------------------------------------------------------------
# keys / JWKS / verifier / client -- all built once at import time so per-example
# work is limited to (cheap) claim variation and a single RS256 signature.
# ---------------------------------------------------------------------------


def _gen_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


SIGNING_KEY = _gen_key()
WRONG_KEY = _gen_key()  # a valid RSA key NOT published in the JWKS


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
) -> str:
    now = int(time.time())
    payload: dict[str, object] = {"sub": sub, "iss": iss, "iat": now, "exp": now + exp_delta}
    if aud is not None:
        payload["aud"] = aud
    if client_id is not None:
        payload["client_id"] = client_id
    return jwt.encode(payload, key, algorithm="RS256", headers={"kid": kid})


def _build_client() -> TestClient:
    app = FastAPI()
    set_verifier(
        app,
        CognitoJwtVerifier(
            region=REGION,
            user_pool_id=USER_POOL_ID,
            app_client_id=CLIENT_ID,
            jwks_provider=static_jwks_provider(JWKS),
        ),
    )

    @app.get("/private")
    def private(user: CurrentUser = Depends(get_current_user)) -> dict:
        return {"sub": user.subject}

    return TestClient(app)


CLIENT = _build_client()


# ---------------------------------------------------------------------------
# strategies
# ---------------------------------------------------------------------------

# Header-safe text: httpx rejects control characters in header values, so we
# keep the random-credential alphabet to printable, JWT-plausible characters.
_HEADER_SAFE = st.text(
    alphabet=string.ascii_letters + string.digits + "-._~+/= .",
    min_size=0,
    max_size=64,
)

_subjects = st.text(
    alphabet=string.ascii_letters + string.digits + "-_",
    min_size=1,
    max_size=32,
)


@st.composite
def invalid_request_headers(draw) -> dict[str, str] | None:
    """Produce headers carrying a missing, malformed, or invalid credential.

    Returns ``None`` to mean "send no ``Authorization`` header at all"; otherwise
    a headers dict whose ``Authorization`` value should never authenticate.
    """

    kind = draw(
        st.sampled_from(
            [
                "missing",          # no Authorization header
                "garbage",          # random non-JWT string as bearer token
                "non_bearer",       # valid token but wrong/garbled scheme
                "empty_bearer",     # "Bearer" with no token
                "wrong_key",        # signed by a key absent from the JWKS
                "expired",          # exp in the past
                "wrong_audience",   # aud/client_id != configured app client
                "wrong_issuer",     # iss from a different user pool
                "unknown_kid",      # header kid not in the JWKS
            ]
        )
    )

    if kind == "missing":
        return None

    if kind == "garbage":
        return {"Authorization": f"Bearer {draw(_HEADER_SAFE)}"}

    if kind == "non_bearer":
        scheme = draw(
            st.sampled_from(["Token", "Basic", "JWT", "bearerish", "", "Bearer{token}"])
        )
        # A structurally valid token presented under the wrong scheme must still
        # be rejected (only the "Bearer <token>" form authenticates).
        value = f"{scheme} {_make_token(sub=draw(_subjects))}".strip()
        return {"Authorization": value}

    if kind == "empty_bearer":
        return {"Authorization": draw(st.sampled_from(["Bearer", "Bearer ", "Bearer    "]))}

    if kind == "wrong_key":
        token = _make_token(key=WRONG_KEY, sub=draw(_subjects))
    elif kind == "expired":
        token = _make_token(exp_delta=draw(st.integers(min_value=-86_400, max_value=-1)),
                            sub=draw(_subjects))
    elif kind == "wrong_audience":
        bad = draw(_subjects)
        # Wrong value placed on either aud (id-token shape) or client_id (access).
        if draw(st.booleans()):
            token = _make_token(aud=bad, sub=draw(_subjects))
        else:
            token = _make_token(aud=None, client_id=bad, sub=draw(_subjects))
    elif kind == "wrong_issuer":
        token = _make_token(
            iss=f"https://cognito-idp.{REGION}.amazonaws.com/{REGION}_{draw(_subjects)}",
            sub=draw(_subjects),
        )
    else:  # unknown_kid
        token = _make_token(kid=draw(_subjects), sub=draw(_subjects))

    return {"Authorization": f"Bearer {token}"}


@st.composite
def valid_request_headers(draw) -> dict[str, str]:
    """Produce headers carrying a validly minted token for the configured pool."""

    sub = draw(_subjects)
    exp_delta = draw(st.integers(min_value=30, max_value=36_000))
    # Either an id-token (app client id on ``aud``) or an access-token
    # (app client id on ``client_id``); both are accepted by the verifier.
    if draw(st.booleans()):
        token = _make_token(sub=sub, exp_delta=exp_delta)
    else:
        token = _make_token(sub=sub, exp_delta=exp_delta, aud=None, client_id=CLIENT_ID)
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# properties
# ---------------------------------------------------------------------------


@settings(max_examples=_ITERATIONS, deadline=None)
@given(headers=invalid_request_headers())
def test_invalid_or_missing_jwt_is_rejected_401(headers: dict[str, str] | None) -> None:
    """Req 16.2: any missing/invalid credential yields 401 on a private route."""

    resp = CLIENT.get("/private") if headers is None else CLIENT.get("/private", headers=headers)
    assert resp.status_code == 401, resp.text


@settings(max_examples=_ITERATIONS, deadline=None)
@given(headers=valid_request_headers())
def test_valid_jwt_is_accepted(headers: dict[str, str]) -> None:
    """Req 16.1: a valid Cognito JWT authenticates -- the route is not 401 (200)."""

    resp = CLIENT.get("/private", headers=headers)
    assert resp.status_code != 401, resp.text
    assert resp.status_code == 200, resp.text
