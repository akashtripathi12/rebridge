"""Unit tests for :class:`S3ObjectStore` using moto to mock S3.

Covers presigned PUT URL issuance (Requirements 2.1, 2.2) and object byte
retrieval. moto stands in for real S3 so no AWS calls are made.
"""

from __future__ import annotations

import boto3
import pytest
from moto import mock_aws

from rebridge_data.models import PresignedUrl
from rebridge_data.s3_object_store import S3ObjectStore

BUCKET = "rebridge-photos-test"


@pytest.fixture
def s3_client():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        yield client


def test_presign_put_returns_put_url_with_default_ttl(s3_client):
    store = S3ObjectStore(BUCKET, client=s3_client)

    presigned = store.presign_put("items/abc/photo-1.jpg")

    assert isinstance(presigned, PresignedUrl)
    assert presigned.method == "PUT"
    assert presigned.expires_in == 300
    assert presigned.url.startswith("https://")
    # The presigned URL targets the requested key in the configured bucket.
    assert BUCKET in presigned.url
    assert "items/abc/photo-1.jpg" in presigned.url


def test_presign_put_honors_custom_ttl(s3_client):
    store = S3ObjectStore(BUCKET, client=s3_client)

    presigned = store.presign_put("items/abc/photo-2.jpg", ttl_seconds=120)

    assert presigned.method == "PUT"
    assert presigned.expires_in == 120


def test_get_bytes_round_trips_a_stored_object(s3_client):
    store = S3ObjectStore(BUCKET, client=s3_client)
    key = "items/abc/photo-3.jpg"
    body = b"\x89PNG\r\n\x1a\n binary photo bytes"
    s3_client.put_object(Bucket=BUCKET, Key=key, Body=body)

    assert store.get_bytes(key) == body


def test_get_bytes_raises_for_missing_object(s3_client):
    store = S3ObjectStore(BUCKET, client=s3_client)

    with pytest.raises(s3_client.exceptions.NoSuchKey):
        store.get_bytes("items/abc/does-not-exist.jpg")
