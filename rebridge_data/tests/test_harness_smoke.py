"""Smoke test confirming the rebridge_data package and test harness are wired."""

import rebridge_data


def test_package_imports():
    assert rebridge_data.__version__ == "0.1.0"
