"""Shared pytest setup."""

import os

# Run Qt without a display so GUI tests open no windows. Set before any Qt import.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
