"""ReBridge API / presentation layer.

FastAPI routers, the Lambda HTTP adapter, the SQS grading worker entrypoint,
Cognito JWT auth, and the dependency-injection composition root. Depends on
``rebridge_service``.

The :func:`rebridge_api.app.create_app` factory and the
:mod:`rebridge_api.dependencies` seam (the :class:`Services` container,
``set_services``/``get_services``, and the ``get_current_user`` auth seam) are
the integration points the auth (17.2), public verify (17.4), Lambda adapter
(17.5), worker (17.6), and composition-root (17.8) tasks attach to.
"""

from rebridge_api.app import create_app
from rebridge_api.auth import (
    AuthError,
    CognitoJwtVerifier,
    JwtVerifier,
    static_jwks_provider,
)
from rebridge_api.dependencies import (
    CurrentUser,
    RequireOperator,
    Services,
    get_current_operator,
    get_current_user,
    get_services,
    get_verifier,
    require_role,
    set_services,
    set_verifier,
)
from rebridge_api.worker import (
    GradingWorker,
    get_worker,
    set_worker,
)
from rebridge_api.wiring import (
    BuiltServices,
    Settings,
    build_app,
    build_services,
    build_worker,
)

__all__: list[str] = [
    "create_app",
    "Services",
    "set_services",
    "get_services",
    "get_current_user",
    "get_current_operator",
    "require_role",
    "RequireOperator",
    "CurrentUser",
    "set_verifier",
    "get_verifier",
    "AuthError",
    "JwtVerifier",
    "CognitoJwtVerifier",
    "static_jwks_provider",
    "GradingWorker",
    "set_worker",
    "get_worker",
    "Settings",
    "BuiltServices",
    "build_services",
    "build_app",
    "build_worker",
]
__version__ = "0.1.0"
