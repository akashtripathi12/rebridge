"""Lambda HTTP adapter for the ReBridge API (task 17.5).

Hosts the FastAPI application on AWS Lambda behind API Gateway by wrapping the
ASGI ``app`` with :class:`mangum.Mangum`. Mangum translates API Gateway (REST
``v1`` and HTTP ``v2``) and Lambda Function URL events into ASGI scope/receive/
send calls, so the same FastAPI app that runs under Uvicorn locally also runs
unchanged on Lambda.

This is the *HTTP* Lambda entrypoint. The asynchronous SQS grading worker has
its own, separate Lambda entrypoint in :mod:`rebridge_api.worker`
(``rebridge_api.worker.lambda_handler``); the two are deployed as distinct
Lambda functions sharing one business-logic core.

Composition-root seam
---------------------
The composition root (task 17.8) builds the configured :class:`FastAPI` app --
wired to concrete data-layer implementations through the
:class:`~rebridge_api.dependencies.Services` container -- and installs it here
via :func:`set_app` *before* the Lambda cold-start imports this module's
``handler``. If no app has been set, :func:`get_app` lazily builds a default
app with :func:`~rebridge_api.app.create_app` so the module stays importable
(and unit-testable) without AWS or any wiring.

Lambda configures the handler entrypoint as ``rebridge_api.http_adapter.handler``.
"""

from __future__ import annotations

from typing import Optional

import threading

from fastapi import FastAPI
from mangum import Mangum

from rebridge_api.app import create_app

__all__ = ["handler", "get_app", "set_app", "reset_app"]

# Module-level slot for the configured app. The composition root sets this; when
# left as ``None`` a default app is built lazily on first access.
_app: Optional[FastAPI] = None
_app_lock = threading.Lock()

def set_app(app: FastAPI) -> None:
    """Install the configured FastAPI app used by the Lambda handler.

    The composition root (task 17.8) calls this with an app wired to concrete
    services before the handler serves its first event.
    """

    global _app
    with _app_lock:
        _app = app


def reset_app() -> None:
    """Clear any installed app (primarily for tests)."""

    global _app
    with _app_lock:
        _app = None


def get_app() -> FastAPI:
    """Return the configured app, building a default one on first use."""

    global _app
    if _app is None:
        with _app_lock:
            if _app is None:
                _app = create_app()
    return _app


_handler: Optional[Mangum] = None
_handler_lock = threading.Lock()

def handler(event, context):
    """Lazy-evaluated Mangum handler for the Lambda entrypoint."""
    global _handler
    if _handler is None:
        with _handler_lock:
            if _handler is None:
                _handler = Mangum(get_app())
    return _handler(event, context)
