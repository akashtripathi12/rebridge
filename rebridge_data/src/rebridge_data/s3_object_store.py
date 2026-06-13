"""boto3-backed :class:`ObjectStore` implementation (Amazon S3).

This concrete gateway issues presigned PUT URLs for direct browser-to-S3 photo
uploads (so image bytes never pass through the API) and retrieves stored object
bytes for the grading pipeline. boto3 is imported here because this is the data
layer -- the only layer permitted to depend on AWS SDKs (see design.md).

Requirements:
- 2.1: one presigned PUT URL per requested photo slot.
- 2.2: presigned upload URLs expire 5 minutes (300 seconds) after issuance.
"""

from __future__ import annotations

import boto3

from rebridge_data.interfaces import ObjectStore
from rebridge_data.models import PresignedUrl

__all__ = ["S3ObjectStore"]


class S3ObjectStore(ObjectStore):
    """Stores and serves photo objects in a single S3 bucket.

    The target bucket name is injected through the constructor by the
    composition root; the boto3 S3 client may also be injected to ease testing
    (e.g. against moto). When omitted, a default client is created.
    """

    def __init__(self, bucket: str, client=None) -> None:
        self._bucket = bucket
        self._client = client if client is not None else boto3.client("s3")

    def presign_put(self, key: str, ttl_seconds: int = 300) -> PresignedUrl:
        """Issue a presigned PUT URL for ``key`` expiring after ``ttl_seconds``.

        The default TTL of 300 seconds satisfies the 5-minute expiry rule
        (Requirement 2.2). The returned :class:`PresignedUrl` records the HTTP
        method (``PUT``) and the TTL so callers can surface it to clients.
        """
        url = self._client.generate_presigned_url(
            "put_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=ttl_seconds,
        )
        return PresignedUrl(url=url, method="PUT", expires_in=ttl_seconds)

    def get_bytes(self, key: str) -> bytes:
        """Fetch the raw bytes of the object stored at ``key``."""
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        return response["Body"].read()
