"""Tests for the Bedrock-backed GradingProvider implementations (Requirement 8).

These cover the two providers behind the swappable grading seam:
``BedrockNovaLiteProvider`` (cascade first, Requirement 8.1) and
``ClaudeVisionProvider`` (cascade fallback, Requirement 8.2). Both must invoke
their model on the photo set plus catalog context and return the model's text
**verbatim and unparsed** as a ``RawModelResponse`` (Requirement 8.4).

Bedrock ``invoke_model`` is not meaningfully supported by moto, so these use a
small injected fake ``bedrock-runtime`` client. The fake captures the request
so we can assert the request shape (model id, that images + catalog are
included) and returns a canned model payload so we can assert the text is
echoed back verbatim with the correct provider name.
"""

import base64
import io
import json

import pytest

from rebridge_data.bedrock_grading_providers import (
    DEFAULT_CLAUDE_VISION_MODEL_ID,
    DEFAULT_NOVA_LITE_MODEL_ID,
    BedrockNovaLiteProvider,
    ClaudeVisionProvider,
)
from rebridge_data.interfaces import GradingProvider
from rebridge_data.models import CatalogContext, RawModelResponse


class _FakeBedrockClient:
    """Captures the last ``invoke_model`` call and returns a canned payload.

    ``response_payload`` is the JSON the model would return; it is serialized
    into a streaming-body-like object exposing ``read()`` to mirror boto3.
    """

    def __init__(self, response_payload: dict) -> None:
        self._response_payload = response_payload
        self.last_kwargs: dict | None = None

    def invoke_model(self, **kwargs):
        self.last_kwargs = kwargs
        raw = json.dumps(self._response_payload).encode("utf-8")
        return {"body": io.BytesIO(raw)}


CATALOG = CatalogContext(
    category="headphones",
    title="Acme Studio Over-Ear",
    expected_components=["earcups", "cable", "case"],
)
IMAGES = [b"\xff\xd8image-one", b"\xff\xd8image-two"]


def _nova_payload(text: str) -> dict:
    return {"output": {"message": {"content": [{"text": text}]}}}


def _claude_payload(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}]}


# --- interface / naming -----------------------------------------------------


def test_providers_implement_grading_provider_interface():
    nova = BedrockNovaLiteProvider(client=_FakeBedrockClient(_nova_payload("x")))
    claude = ClaudeVisionProvider(client=_FakeBedrockClient(_claude_payload("x")))
    assert isinstance(nova, GradingProvider)
    assert isinstance(claude, GradingProvider)


def test_provider_names_are_stable():
    nova = BedrockNovaLiteProvider(client=_FakeBedrockClient(_nova_payload("x")))
    claude = ClaudeVisionProvider(client=_FakeBedrockClient(_claude_payload("x")))
    assert nova.name == "nova-lite"
    assert claude.name == "claude-vision"


def test_default_model_ids():
    nova = BedrockNovaLiteProvider(client=_FakeBedrockClient(_nova_payload("x")))
    claude = ClaudeVisionProvider(client=_FakeBedrockClient(_claude_payload("x")))
    assert nova.model_id == DEFAULT_NOVA_LITE_MODEL_ID
    assert claude.model_id == DEFAULT_CLAUDE_VISION_MODEL_ID


def test_model_id_is_injectable():
    fake = _FakeBedrockClient(_nova_payload("x"))
    provider = BedrockNovaLiteProvider(model_id="custom.model:1", client=fake)
    provider.grade(IMAGES, CATALOG)
    assert provider.model_id == "custom.model:1"
    assert fake.last_kwargs["modelId"] == "custom.model:1"


# --- Nova Lite --------------------------------------------------------------


def test_nova_request_includes_model_id_images_and_catalog():
    fake = _FakeBedrockClient(_nova_payload("graded"))
    provider = BedrockNovaLiteProvider(client=fake)
    provider.grade(IMAGES, CATALOG)

    assert fake.last_kwargs["modelId"] == DEFAULT_NOVA_LITE_MODEL_ID
    body = json.loads(fake.last_kwargs["body"])
    content = body["messages"][0]["content"]

    # Catalog context is present in the text block.
    text_blocks = [b["text"] for b in content if "text" in b]
    joined = "\n".join(text_blocks)
    assert "headphones" in joined
    assert "Acme Studio Over-Ear" in joined
    assert "earcups" in joined

    # Every image is included, base64-encoded, in order.
    image_blocks = [b["image"] for b in content if "image" in b]
    assert len(image_blocks) == len(IMAGES)
    for original, block in zip(IMAGES, image_blocks):
        assert block["source"]["bytes"] == base64.b64encode(original).decode("ascii")


def test_nova_returns_model_text_verbatim():
    fake = _FakeBedrockClient(_nova_payload('{"grade": "B", "confidence": 0.7}'))
    provider = BedrockNovaLiteProvider(client=fake)

    result = provider.grade(IMAGES, CATALOG)

    assert isinstance(result, RawModelResponse)
    assert result.provider_name == "nova-lite"
    assert result.content == '{"grade": "B", "confidence": 0.7}'


# --- Claude vision ----------------------------------------------------------


def test_claude_request_includes_model_id_images_and_catalog():
    fake = _FakeBedrockClient(_claude_payload("graded"))
    provider = ClaudeVisionProvider(client=fake)
    provider.grade(IMAGES, CATALOG)

    assert fake.last_kwargs["modelId"] == DEFAULT_CLAUDE_VISION_MODEL_ID
    body = json.loads(fake.last_kwargs["body"])
    content = body["messages"][0]["content"]

    text_blocks = [b["text"] for b in content if b.get("type") == "text"]
    joined = "\n".join(text_blocks)
    assert "headphones" in joined
    assert "Acme Studio Over-Ear" in joined
    assert "case" in joined

    image_blocks = [b for b in content if b.get("type") == "image"]
    assert len(image_blocks) == len(IMAGES)
    for original, block in zip(IMAGES, image_blocks):
        assert block["source"]["data"] == base64.b64encode(original).decode("ascii")


def test_claude_returns_model_text_verbatim():
    fake = _FakeBedrockClient(_claude_payload("free-form summary text"))
    provider = ClaudeVisionProvider(client=fake)

    result = provider.grade(IMAGES, CATALOG)

    assert isinstance(result, RawModelResponse)
    assert result.provider_name == "claude-vision"
    assert result.content == "free-form summary text"


# --- edge cases -------------------------------------------------------------


def test_prompt_omits_optional_fields_when_absent():
    fake = _FakeBedrockClient(_nova_payload("ok"))
    provider = BedrockNovaLiteProvider(client=fake)
    minimal = CatalogContext(category="toys")
    provider.grade([b"img"], minimal)

    body = json.loads(fake.last_kwargs["body"])
    content = body["messages"][0]["content"]
    joined = "\n".join(b["text"] for b in content if "text" in b)
    assert "toys" in joined
    assert "Title:" not in joined
    assert "Expected components:" not in joined


def test_grade_with_no_images_still_sends_catalog():
    fake = _FakeBedrockClient(_claude_payload("ok"))
    provider = ClaudeVisionProvider(client=fake)
    provider.grade([], CATALOG)

    body = json.loads(fake.last_kwargs["body"])
    content = body["messages"][0]["content"]
    assert any(b.get("type") == "text" for b in content)
    assert not any(b.get("type") == "image" for b in content)
