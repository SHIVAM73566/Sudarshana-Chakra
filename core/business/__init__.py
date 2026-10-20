"""Enterprise business vertical toolkits for Sudarshana Chakra AI.

Each vertical is a standalone module exposing the registry contract
(``FEATURE_METADATA`` + ``execute(**kwargs) -> dict``) and persisting through the
shared :mod:`core.business.db` SQLite store with at-rest encryption and
Excel/CSV export.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "inventory",
    "procurement",
    "finance",
    "manufacturing",
    "marketing",
]
