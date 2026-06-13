"""Unit tests for :class:`rebridge_data.kms_card_signer.KmsCardSigner`.

Testing note
------------
``KmsCardSigner`` is exercised against an injected fake KMS client that computes
a real HMAC-SHA256 MAC with a fixed in-test key, plus a ``botocore`` ``Stubber``
smoke test for the ``GenerateMac`` wire call. We deliberately do *not* use
``moto`` here: ``moto``'s KMS ``GenerateMac``/``VerifyMac`` support is limited
and does not reliably produce a stable, verifiable MAC across calls, which is
exactly what a sign/verify round-trip needs. The fake client gives deterministic
HMAC behavior so the round-trip, tamper-detection, base64 encoding, and
constant-time comparison logic in ``KmsCardSigner`` are all genuinely
validated. Real end-to-end KMS sign/verify is covered separately as a data-layer
integration smoke test (task 16.11).
"""

from __future__ import annotations

import base64
import hashlib
import hmac

import boto3
import pytest
from botocore.stub import Stubber

from rebridge_data.kms_card_signer import KmsCardSigner

# Fixed symmetric key the fake KMS client uses to emulate an HMAC_256 KMS key.
_FAKE_KEY_MATERIAL = b"unit-test-hmac-key-material-0123456789"
_KEY_ID = "alias/rebridge-card-hmac"


class FakeKmsClient:
    """Minimal stand-in for a boto3 KMS client's ``generate_mac`` call.

    Computes a real HMAC-SHA256 over the message with a fixed key so that
    repeated calls for the same payload return identical MACs (enabling
    verification round-trips) and different payloads return different MACs.
    """

    def __init__(self, key_material: bytes = _FAKE_KEY_MATERIAL) -> None:
        self._key_material = key_material
        self.generate_mac_calls: list[dict] = []

    def generate_mac(self, *, KeyId: str, Message: bytes, MacAlgorithm: str) -> dict:
        self.generate_mac_calls.append(
            {"KeyId": KeyId, "Message": Message, "MacAlgorithm": MacAlgorithm}
        )
        assert MacAlgorithm == "HMAC_SHA_256"
        mac = hmac.new(self._key_material, Message, hashlib.sha256).digest()
        return {"Mac": mac, "MacAlgorithm": MacAlgorithm, "KeyId": KeyId}


@pytest.fixture
def signer() -> KmsCardSigner:
    return KmsCardSigner(_KEY_ID, client=FakeKmsClient())


def test_sign_returns_base64_of_hmac_sha256(signer: KmsCardSigner) -> None:
    payload = b"card-1|item-1|GOOD|2024-01-01T00:00:00Z"

    signature = signer.sign(payload)

    expected_mac = hmac.new(_FAKE_KEY_MATERIAL, payload, hashlib.sha256).digest()
    assert signature == base64.b64encode(expected_mac).decode("ascii")
    # A 32-byte HMAC-SHA256 digest base64-encodes to 44 ASCII characters.
    assert len(signature) == 44


def test_sign_passes_key_id_and_algorithm_to_kms() -> None:
    client = FakeKmsClient()
    signer = KmsCardSigner(_KEY_ID, client=client)

    signer.sign(b"payload")

    assert client.generate_mac_calls == [
        {"KeyId": _KEY_ID, "Message": b"payload", "MacAlgorithm": "HMAC_SHA_256"}
    ]


def test_sign_verify_round_trip(signer: KmsCardSigner) -> None:
    payload = b"card-42|item-7|EXCELLENT|2024-06-15T12:00:00Z"

    signature = signer.sign(payload)

    assert signer.verify(payload, signature) is True


def test_verify_rejects_tampered_payload(signer: KmsCardSigner) -> None:
    payload = b"card-42|item-7|EXCELLENT|2024-06-15T12:00:00Z"
    signature = signer.sign(payload)

    tampered = b"card-42|item-7|POOR|2024-06-15T12:00:00Z"

    assert signer.verify(tampered, signature) is False


def test_verify_rejects_tampered_signature(signer: KmsCardSigner) -> None:
    payload = b"card-42|item-7|EXCELLENT|2024-06-15T12:00:00Z"
    signature = signer.sign(payload)

    # Flip the first base64 character to a different valid character.
    flipped = ("B" if signature[0] != "B" else "C") + signature[1:]

    assert signer.verify(payload, flipped) is False


def test_verify_returns_false_for_malformed_base64(signer: KmsCardSigner) -> None:
    # Not valid base64 (contains characters outside the alphabet / bad padding).
    assert signer.verify(b"payload", "not valid base64!!!") is False
    assert signer.verify(b"payload", "") is False


def test_verify_is_deterministic_across_signers() -> None:
    # Two signers backed by the same key material agree, modeling sign on the
    # worker and verify on the public endpoint sharing one KMS key.
    payload = b"card-9|item-9|GOOD|2024-02-02T00:00:00Z"
    signing = KmsCardSigner(_KEY_ID, client=FakeKmsClient())
    verifying = KmsCardSigner(_KEY_ID, client=FakeKmsClient())

    signature = signing.sign(payload)

    assert verifying.verify(payload, signature) is True


def test_generate_mac_wire_call_with_botocore_stubber() -> None:
    """Smoke test: the signer issues a well-formed GenerateMac request."""
    client = boto3.client("kms", region_name="us-east-1")
    payload = b"card-1|item-1|GOOD|2024-01-01T00:00:00Z"
    canned_mac = hmac.new(_FAKE_KEY_MATERIAL, payload, hashlib.sha256).digest()

    stubber = Stubber(client)
    stubber.add_response(
        "generate_mac",
        {"Mac": canned_mac, "MacAlgorithm": "HMAC_SHA_256", "KeyId": _KEY_ID},
        expected_params={
            "KeyId": _KEY_ID,
            "Message": payload,
            "MacAlgorithm": "HMAC_SHA_256",
        },
    )

    signer = KmsCardSigner(_KEY_ID, client=client)
    with stubber:
        signature = signer.sign(payload)

    assert signature == base64.b64encode(canned_mac).decode("ascii")
    stubber.assert_no_pending_responses()
