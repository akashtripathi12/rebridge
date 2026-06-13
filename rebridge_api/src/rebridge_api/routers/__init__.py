"""FastAPI routers for the ReBridge API.

Each router maps a slice of the API contract to service calls and is included by
the :func:`rebridge_api.app.create_app` factory. Keeping routers in their own
package lets later tasks (the public verify route in 17.4, etc.) add modules and
attach them to the same app without editing existing routers.
"""

from rebridge_api.routers import items, listings, marketplace

__all__ = ["items", "listings", "marketplace"]
