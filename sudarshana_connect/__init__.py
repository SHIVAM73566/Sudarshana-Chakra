"""Sudarshana Connect subsystem.

This package adds the local gateway, device registry, pairing flow, and
protocol definitions used by Sudarshana AI to reach companion devices.
"""

from .service import SudarshanaConnectService, get_service

__all__ = ["SudarshanaConnectService", "get_service"]
