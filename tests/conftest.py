# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Pytest configuration."""

# tests/conftest.py
import sys
from pathlib import Path

src_dir = Path(__file__).parent.parent / "src"
sys.path.append(str(src_dir))
sys.path.append(str("lib"))
