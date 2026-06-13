#!/usr/bin/env python
"""Shared test runner for the ReBridge backend monorepo.

Runs the test suite for each package, or all of them. Each package's suite is
executed from inside that package's own directory so the installed package
resolves cleanly (running from the repo root would let the top-level package
folders shadow the installed `src/` packages).

Usage:
    python run_tests.py            # run every package's suite
    python run_tests.py data       # run only rebridge_data
    python run_tests.py service    # run only rebridge_service
    python run_tests.py api        # run only rebridge_api

Before running, install the three packages in editable mode (dependency order
is handled automatically when installed together)::

    pip install -e ./rebridge_data[test] -e ./rebridge_service[test] -e ./rebridge_api[test]
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Map a short name to the package directory. Order reflects the one-way
# dependency direction data -> service -> api.
PACKAGES = {
    "data": "rebridge_data",
    "service": "rebridge_service",
    "api": "rebridge_api",
}


def main(argv: list[str]) -> int:
    selected = argv[1:] if len(argv) > 1 else list(PACKAGES)
    unknown = [name for name in selected if name not in PACKAGES]
    if unknown:
        print(f"Unknown package(s): {', '.join(unknown)}", file=sys.stderr)
        print(f"Choose from: {', '.join(PACKAGES)}", file=sys.stderr)
        return 2

    overall = 0
    for name in selected:
        pkg_dir = ROOT / PACKAGES[name]
        cmd = [sys.executable, "-m", "pytest", "tests"]
        print(f"\n=== {name} :: {' '.join(cmd)} (cwd={pkg_dir}) ===")
        rc = subprocess.call(cmd, cwd=pkg_dir)
        # pytest exit code 5 == "no tests collected"; treat as non-fatal so an
        # empty suite at this early stage still reports success.
        if rc == 5:
            print(f"(no tests collected for {name})")
            rc = 0
        overall = overall or rc
    return overall


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
