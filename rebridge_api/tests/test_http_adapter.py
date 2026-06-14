"""Unit tests for the Lambda HTTP adapter (task 17.5).

Confirms the module exposes a Mangum handler wrapping a FastAPI app, that the
composition-root seam (``set_app``/``get_app``) works, and that a public route
(GET /healthz) returns 200 when invoked through Mangum with an API Gateway v2
event -- exercising the full ASGI translation path without AWS.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from mangum import Mangum

from rebridge_api import create_app
from rebridge_api import http_adapter


@pytest.fixture(autouse=True)
def _reset_module_app():
    """Keep the module-level app slot isolated between tests."""
    http_adapter.reset_app()
    yield
    http_adapter.reset_app()


def test_handler_is_mangum_function():
    assert callable(http_adapter.handler)


def test_handler_wraps_a_fastapi_app():
    http_adapter.handler(_apigw_v2_get_event("/healthz"), None)
    assert isinstance(http_adapter._handler.app, FastAPI)


def test_get_app_builds_default_app_lazily():
    app = http_adapter.get_app()
    assert isinstance(app, FastAPI)
    # Cached: a second call returns the same instance.
    assert http_adapter.get_app() is app


def test_set_app_overrides_for_composition_root():
    configured = create_app()
    http_adapter.set_app(configured)
    assert http_adapter.get_app() is configured


def _apigw_v2_get_event(path: str) -> dict:
    """Minimal API Gateway HTTP API (payload format v2.0) GET event."""
    return {
        "version": "2.0",
        "routeKey": f"GET {path}",
        "rawPath": path,
        "rawQueryString": "",
        "headers": {"host": "test", "accept": "application/json"},
        "requestContext": {
            "http": {
                "method": "GET",
                "path": path,
                "protocol": "HTTP/1.1",
                "sourceIp": "127.0.0.1",
            },
            "stage": "$default",
        },
        "isBase64Encoded": False,
    }


def test_healthz_returns_200_through_mangum():
    """A public route is reachable end-to-end through the Mangum adapter."""
    handler = Mangum(create_app())
    response = handler(_apigw_v2_get_event("/healthz"), None)
    assert response["statusCode"] == 200
    assert "ok" in response["body"]
