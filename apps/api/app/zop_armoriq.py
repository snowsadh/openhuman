"""Temporary module alias for the former Zop-specific module name."""

import sys

from app import armoriq_runtime as _runtime

sys.modules[__name__] = _runtime
