#!/usr/bin/env python3
"""Run the integration's tests without installing Home Assistant.

The integration targets Home Assistant, which is not vendored here.
``tests/_stubs`` provides import-only stand-ins for the Home Assistant and bleak
modules the integration touches, so the measurement state machine can be tested
as plain Python. This is a regression harness for the state machine, not a
substitute for testing against a real Home Assistant instance.

Usage:
    python3 tests/run_tests.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))

import conftest  # noqa: E402,F401  (installs the stubs on sys.path)


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=str(TESTS), pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
