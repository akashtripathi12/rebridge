"""boto3-backed :class:`GradingProvider` implementations (Amazon Bedrock).

These two concrete providers sit behind the swappable grading seam
(:class:`~rebridge_data.interfaces.GradingProvider`, Requirement 8.4) and are
invoked by the service-layer ``GradingEngine`` in cascade order: Bedrock Nova
Lite first (Requirement 8.1) and Claude vision as the fallback (Requirement
8.2). Each wraps a single Bedrock vision model.

A provider's only job is to invoke its model on the photo set plus the catalog
context and return the model's response **verbatim and unparsed** as a
:class:`~rebridge_data.models.RawModelResponse`. Strict JSON parsing against the
grade-assessment schema happens later in the service layer; keeping parsing out
of the data layer is what lets an alternate provider be substituted without
changing the grade-assessment schema (Requirement 8.4).

``boto3`` is imported here because this is the data layer -- the only layer
permitted to depend on AWS SDKs (see design.md). Both the model id and the
``bedrock-runtime`` client are injected through the constructor so the
composition root can pin them and tests can supply a fake client.
"""

from __future__ import annotations

import base64
import json
from abc import abstractmethod
from typing import Any

import boto3

from rebridge_data.interfaces import GradingProvider
from rebridge_data.models import CatalogContext, RawModelResponse

__all__ = [
    "BedrockNovaLiteProvider",
    "ClaudeVisionProvider",
]

# Default Bedrock model identifiers for the cascade. They are overridable via
# the constructor so the composition root can pin exact versions per region.
DEFAULT_NOVA_LITE_MODEL_ID = "amazon.nova-lite-v1:0"
DEFAULT_CLAUDE_VISION_MODEL_ID = "anthropic.claude-3-5-sonnet-20240620-v1:0"

# Stable provider identifiers used for cascade ordering and logging.
_NOVA_LITE_NAME = "nova-lite"
_CLAUDE_VISION_NAME = "claude-vision"

# All photos are submitted to Bedrock as JPEG; the upload path normalises to it.
_IMAGE_FORMAT = "jpeg"
_IMAGE_MEDIA_TYPE = "image/jpeg"


def _build_prompt(catalog: CatalogContext) -> str:
    """Compose the textual grading instruction from the catalog context.

    The catalog reference data (category, optional title, and the list of
    expected components) is folded into the prompt so the model can reason about
    completeness and defects against what the item is supposed to be. The
    grade-assessment JSON schema itself is enforced downstream in the service
    layer, so this prompt only asks the model to assess the photos.
    """
    lines = [
        "You are grading the condition of a returned or pre-owned item from its photos.",
        f"Category: {catalog.category}",
    ]
    if catalog.title:
        lines.append(f"Title: {catalog.title}")
    if catalog.expected_components:
        lines.append(
            "Expected components: " + ", ".join(catalog.expected_components)
        )
    lines.append(
        "Assess the item's condition, list any visible defects with their "
        "location and severity, and check completeness against the expected "
        "components."
    )
    return "\n".join(lines)


class _BedrockGradingProvider(GradingProvider):
    """Shared invoke-and-extract scaffolding for the Bedrock vision providers.

    Subclasses supply the model-specific request body and response-text
    extraction; this base owns the constructor (model id + injected client),
    the ``name`` property, and the ``invoke_model`` round-trip.
    """

    _provider_name: str
    _default_model_id: str

    def __init__(
        self,
        model_id: str | None = None,
        client: Any | None = None,
        region_name: str | None = None,
    ) -> None:
        self._model_id = model_id if model_id is not None else self._default_model_id
        if client is not None:
            self._client = client
        elif region_name is not None:
            self._client = boto3.client("bedrock-runtime", region_name=region_name)
        else:
            self._client = boto3.client("bedrock-runtime")

    @property
    def name(self) -> str:
        """Stable provider identifier used for cascade ordering and logging."""
        return self._provider_name

    @property
    def model_id(self) -> str:
        """The Bedrock model id this provider invokes."""
        return self._model_id

    def grade(
        self, images: list[bytes], catalog: CatalogContext
    ) -> RawModelResponse:
        """Invoke the model on ``images`` + ``catalog`` and return the raw text.

        The model's text output is returned verbatim in
        :attr:`RawModelResponse.content`; no parsing or validation is performed
        here (Requirement 8.4).
        """
        body = self._build_body(images, catalog)
        response = self._client.invoke_model(
            modelId=self._model_id,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )
        payload = json.loads(_read_body(response["body"]))
        text = self._extract_text(payload)
        return RawModelResponse(provider_name=self._provider_name, content=text)

    @abstractmethod
    def _build_body(
        self, images: list[bytes], catalog: CatalogContext
    ) -> dict[str, Any]:
        """Build the model-specific ``invoke_model`` request body."""

    @abstractmethod
    def _extract_text(self, payload: dict[str, Any]) -> str:
        """Extract the model's verbatim text output from the response payload."""


def _read_body(body: Any) -> str | bytes:
    """Read an ``invoke_model`` response body.

    Real boto3 returns a streaming body exposing ``read()``; tests may inject a
    plain ``str``/``bytes`` to keep the fake client simple.
    """
    if hasattr(body, "read"):
        return body.read()
    return body


class BedrockNovaLiteProvider(_BedrockGradingProvider):
    """First provider in the cascade: Amazon Nova Lite (Requirement 8.1).

    Uses the Amazon Nova ``invoke_model`` message schema, where each image is a
    base64-encoded ``{"image": {"format", "source": {"bytes"}}}`` content block.
    """

    _provider_name = _NOVA_LITE_NAME
    _default_model_id = DEFAULT_NOVA_LITE_MODEL_ID

    def _build_body(
        self, images: list[bytes], catalog: CatalogContext
    ) -> dict[str, Any]:
        content: list[dict[str, Any]] = [{"text": _build_prompt(catalog)}]
        for image in images:
            content.append(
                {
                    "image": {
                        "format": _IMAGE_FORMAT,
                        "source": {
                            "bytes": base64.b64encode(image).decode("ascii")
                        },
                    }
                }
            )
        return {
            "messages": [{"role": "user", "content": content}],
            "inferenceConfig": {"maxTokens": 1024, "temperature": 0.0},
        }

    def _extract_text(self, payload: dict[str, Any]) -> str:
        blocks = payload["output"]["message"]["content"]
        return "".join(block.get("text", "") for block in blocks)


class ClaudeVisionProvider(_BedrockGradingProvider):
    """Fallback provider in the cascade: Claude vision (Requirement 8.2).

    Uses the Anthropic messages ``invoke_model`` schema on Bedrock, where each
    image is a base64-encoded ``{"type": "image", "source": {...}}`` content
    block alongside the textual grading instruction.
    """

    _provider_name = _CLAUDE_VISION_NAME
    _default_model_id = DEFAULT_CLAUDE_VISION_MODEL_ID

    def _build_body(
        self, images: list[bytes], catalog: CatalogContext
    ) -> dict[str, Any]:
        content: list[dict[str, Any]] = [
            {"type": "text", "text": _build_prompt(catalog)}
        ]
        for image in images:
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": _IMAGE_MEDIA_TYPE,
                        "data": base64.b64encode(image).decode("ascii"),
                    },
                }
            )
        return {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1024,
            "temperature": 0.0,
            "messages": [{"role": "user", "content": content}],
        }

    def _extract_text(self, payload: dict[str, Any]) -> str:
        blocks = payload["content"]
        return "".join(
            block.get("text", "")
            for block in blocks
            if block.get("type", "text") == "text"
        )
