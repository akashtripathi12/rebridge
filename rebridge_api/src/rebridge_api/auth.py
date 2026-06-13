"""Cognito JWT verification for private routes (task 17.2).

The API's private routes require a valid Cognito-issued JWT (Requirements 16.1,
16.2). This module provides the *verifier* the auth dependency
(:func:`rebridge_api.dependencies.get_current_user`) uses to turn a raw bearer
token into a set of trusted claims -- or to reject it.

Design goals
------------
* **Real validation.** :class:`CognitoJwtVerifier` checks the RS256 signature
  against the user pool's JWKS, the ``iss`` (issuer) claim, token expiry, and
  the app client id (``aud`` for id-tokens / ``client_id`` for access-tokens).
* **Injectable / testable.** The JWKS is supplied through a ``jwks_provider``
  callable, so a test can hand the verifier a locally generated RSA public key
  as a fake JWKS and never touch Cognito. The composition root (task 17.8) wires
  a real network-backed provider via :meth:`CognitoJwtVerifier.from_cognito`.
* **No import-time network.** Providers fetch lazily and cache; constructing a
  verifier never performs I/O.

The verifier raises :class:`AuthError` for every rejection reason (missing,
malformed, bad signature, expired, wrong issuer/audience); the auth dependency
maps that single failure type to HTTP 401.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol, Sequence, runtime_checkable

import jwt
from jwt import PyJWK, PyJWKSet

__all__ = [
    "AuthError",
    "JwtVerifier",
    "CognitoJwtVerifier",
    "CachingJwksProvider",
    "static_jwks_provider",
]


class AuthError(Exception):
    """Raised when a token is missing, malformed, or fails validation.

    The auth dependency catches this and responds with HTTP 401; the message is
    intentionally coarse so it can be surfaced without leaking token internals.
    """


@runtime_checkable
class JwtVerifier(Protocol):
    """The seam the auth dependency depends on.

    Any object exposing ``verify(token) -> claims`` (raising :class:`AuthError`
    on rejection) can stand in for the real Cognito verifier, which keeps the
    dependency overridable and the tests free of AWS.
    """

    def verify(self, token: str) -> dict[str, Any]:  # pragma: no cover - protocol
        ...


JwksProvider = Callable[[], Mapping[str, Any]]
"""A zero-arg callable returning a JWKS document (``{"keys": [...]}``)."""


def static_jwks_provider(jwks: Mapping[str, Any]) -> JwksProvider:
    """Return a provider that always yields the given JWKS document.

    Handy for tests: pass a JWKS built from a locally generated RSA public key.
    """

    return lambda: jwks


@dataclass
class CachingJwksProvider:
    """Fetch a JWKS document from a URL, caching it for ``ttl_seconds``.

    Cognito publishes its keys at
    ``{issuer}/.well-known/jwks.json`` and rotates them rarely, so a short-lived
    in-process cache avoids a network round-trip on every request without
    pinning a stale key set forever. Thread-safe so concurrent Lambda handler
    threads share one fetch.
    """

    url: str
    ttl_seconds: float = 3600.0
    _opener: Callable[[str], bytes] = field(default=None, repr=False)  # type: ignore[assignment]
    _cached: Mapping[str, Any] | None = field(default=None, init=False, repr=False)
    _fetched_at: float = field(default=0.0, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def __call__(self) -> Mapping[str, Any]:
        now = time.monotonic()
        with self._lock:
            if self._cached is not None and (now - self._fetched_at) < self.ttl_seconds:
                return self._cached
            raw = self._fetch()
            try:
                doc = json.loads(raw)
            except json.JSONDecodeError as exc:  # pragma: no cover - network shape
                raise AuthError("could not parse JWKS document") from exc
            self._cached = doc
            self._fetched_at = now
            return doc

    def _fetch(self) -> bytes:
        if self._opener is not None:
            return self._opener(self.url)
        with urllib.request.urlopen(self.url, timeout=5) as resp:  # noqa: S310 - https only
            return resp.read()


@dataclass
class CognitoJwtVerifier:
    """Validate a Cognito-issued JWT against a user pool's JWKS.

    Parameters
    ----------
    region:
        AWS region of the user pool (e.g. ``"us-east-1"``).
    user_pool_id:
        The Cognito user pool id (e.g. ``"us-east-1_abc123"``).
    app_client_id:
        The app client id the token must be issued for. Matched against the
        ``aud`` claim (id-tokens) and the ``client_id`` claim (access-tokens).
    jwks_provider:
        Zero-arg callable returning the user pool's JWKS document. Injected so
        tests can supply a fake key set and production can supply a caching
        network fetcher.
    leeway:
        Allowed clock skew (seconds) applied to time-based claims.
    algorithms:
        Permitted signing algorithms; Cognito uses ``RS256``.
    """

    region: str
    user_pool_id: str
    app_client_id: str
    jwks_provider: JwksProvider
    leeway: float = 0.0
    algorithms: Sequence[str] = ("RS256",)

    @property
    def issuer(self) -> str:
        """The expected ``iss`` claim for tokens from this user pool."""

        return f"https://cognito-idp.{self.region}.amazonaws.com/{self.user_pool_id}"

    @classmethod
    def from_cognito(
        cls,
        *,
        region: str,
        user_pool_id: str,
        app_client_id: str,
        jwks_ttl_seconds: float = 3600.0,
        leeway: float = 0.0,
    ) -> "CognitoJwtVerifier":
        """Build a verifier whose JWKS is fetched (and cached) from Cognito.

        The composition root (task 17.8) uses this to wire the real verifier
        from configuration without performing any network I/O until the first
        token is validated.
        """

        issuer = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}"
        provider = CachingJwksProvider(
            url=f"{issuer}/.well-known/jwks.json", ttl_seconds=jwks_ttl_seconds
        )
        return cls(
            region=region,
            user_pool_id=user_pool_id,
            app_client_id=app_client_id,
            jwks_provider=provider,
            leeway=leeway,
        )

    def verify(self, token: str) -> dict[str, Any]:
        """Return the trusted claims for ``token`` or raise :class:`AuthError`.

        Validation order: presence -> resolve signing key by ``kid`` from the
        JWKS -> verify signature, issuer, and expiry -> verify the app client id.
        """

        if not token:
            raise AuthError("missing token")

        signing_key = self._signing_key(token)

        try:
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=list(self.algorithms),
                issuer=self.issuer,
                leeway=self.leeway,
                # We verify the app-client id ourselves below because Cognito
                # carries it as `aud` (id-tokens) OR `client_id` (access-tokens).
                options={"require": ["exp", "iss"], "verify_aud": False},
            )
        except jwt.PyJWTError as exc:
            raise AuthError(f"token validation failed: {exc}") from exc

        self._verify_app_client(claims)
        return claims

    def _signing_key(self, token: str) -> PyJWK:
        """Resolve the JWKS key matching the token header's ``kid``."""

        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise AuthError("malformed token header") from exc

        kid = header.get("kid")
        if not kid:
            raise AuthError("token header missing 'kid'")

        try:
            jwk_set = PyJWKSet.from_dict(dict(self.jwks_provider()))
        except Exception as exc:  # noqa: BLE001 - any JWKS shape problem is an auth failure
            raise AuthError("could not load signing keys") from exc

        for key in jwk_set.keys:
            if key.key_id == kid:
                return key
        raise AuthError(f"no signing key for kid {kid!r}")

    def _verify_app_client(self, claims: Mapping[str, Any]) -> None:
        """Ensure the token was issued for the configured app client id."""

        candidates: list[str] = []
        aud = claims.get("aud")
        if isinstance(aud, str):
            candidates.append(aud)
        elif isinstance(aud, (list, tuple)):
            candidates.extend(str(a) for a in aud)
        client_id = claims.get("client_id")
        if isinstance(client_id, str):
            candidates.append(client_id)

        if self.app_client_id not in candidates:
            raise AuthError("token is not for this app client")
