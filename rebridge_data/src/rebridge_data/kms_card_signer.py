"""KMS-backed Product Health Card signer.

Concrete :class:`~rebridge_data.interfaces.CardSigner` implementation that signs
and verifies the canonical Product_Health_Card payload using HMAC-SHA256 with a
key managed by AWS KMS (Requirement 11.2, 12.1).

The key material never leaves KMS: signing calls the KMS ``GenerateMac`` API
(``MacAlgorithm=HMAC_SHA_256``) with an injected ``key_id`` and base64-encodes
the returned MAC into the signature string. Verification recomputes the MAC the
same way and compares it against the supplied signature in constant time, which
matches the "recompute-and-compare" contract of the interface while keeping the
secret inside KMS.

``boto3`` is imported here because the data layer is the only layer permitted to
depend on it. The KMS client is injectable so the signer can be exercised
against a stub/fake in tests without real AWS calls.
"""

from __future__ import annotations

import base64
import binascii
import hmac
from typing import Any

import boto3

from rebridge_data.interfaces import CardSigner

__all__ = ["KmsCardSigner"]

# KMS MAC algorithm for an HMAC_256 KMS key. The KMS key referenced by
# ``key_id`` must be an HMAC key created with this spec.
_MAC_ALGORITHM = "HMAC_SHA_256"


class KmsCardSigner(CardSigner):
    """Sign/verify card payloads with a KMS-managed HMAC-SHA256 key.

    Args:
        key_id: The KMS key identifier (key id, ARN, or alias) of the HMAC_256
            key used to generate the MAC.
        client: Optional pre-built KMS client (or any object exposing a
            ``generate_mac`` method). When omitted, a boto3 ``kms`` client is
            constructed. Injecting a client keeps unit tests free of real AWS
            calls.
        region_name: Optional region used only when constructing the default
            boto3 client.
    """

    def __init__(
        self,
        key_id: str,
        *,
        client: Any | None = None,
        region_name: str | None = None,
    ) -> None:
        self._key_id = key_id
        self._client = (
            client
            if client is not None
            else boto3.client("kms", region_name=region_name)
        )

    def sign(self, payload: bytes) -> str:
        """Return the base64-encoded HMAC-SHA256 signature of ``payload``."""
        mac = self._generate_mac(payload)
        return base64.b64encode(mac).decode("ascii")

    def verify(self, payload: bytes, signature: str) -> bool:
        """Recompute the MAC for ``payload`` and constant-time compare it.

        Returns ``True`` only when ``signature`` is a valid base64 encoding of
        the MAC that KMS produces for ``payload``. Malformed signatures yield
        ``False`` rather than raising.
        """
        try:
            provided = base64.b64decode(signature, validate=True)
        except (binascii.Error, ValueError):
            return False
        expected = self._generate_mac(payload)
        # Constant-time comparison to avoid leaking match length via timing.
        return hmac.compare_digest(provided, expected)

    def _generate_mac(self, payload: bytes) -> bytes:
        response = self._client.generate_mac(
            KeyId=self._key_id,
            Message=payload,
            MacAlgorithm=_MAC_ALGORITHM,
        )
        return response["Mac"]
