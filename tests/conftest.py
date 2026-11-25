"""Test harness setup.

The integration targets Home Assistant, which this repository does not vendor.
``tests/_stubs`` provides the smallest import-only stand-ins for the Home
Assistant and bleak modules that ``custom_components.yunmai_scale`` touches, so
the measurement state machine can be exercised without a running instance.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
STUBS = Path(__file__).resolve().parent / "_stubs"

for path in (str(STUBS), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)
