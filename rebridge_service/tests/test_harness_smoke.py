"""Smoke test confirming the rebridge_service package and test harness are wired."""

import rebridge_service


def test_package_imports():
    assert rebridge_service.__version__ == "0.1.0"


def test_service_can_see_data_layer():
    # The one-way dependency service -> data must resolve at import time.
    import rebridge_data

    assert rebridge_data.__version__ == "0.1.0"
