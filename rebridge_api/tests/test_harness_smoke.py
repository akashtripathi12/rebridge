"""Smoke test confirming the rebridge_api package and test harness are wired."""

import rebridge_api


def test_package_imports():
    assert rebridge_api.__version__ == "0.1.0"


def test_api_can_see_service_layer():
    # The one-way dependency api -> service must resolve at import time.
    import rebridge_service

    assert rebridge_service.__version__ == "0.1.0"
