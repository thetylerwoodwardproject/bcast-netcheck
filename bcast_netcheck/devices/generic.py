"""Interface for future device integrations; no vendor behavior is loaded in 0.1."""

from typing import Protocol

from bcast_netcheck.config import Endpoint, Settings
from bcast_netcheck.models import CheckResult


class DevicePlugin(Protocol):
    async def check(self, endpoint: Endpoint, settings: Settings) -> list[CheckResult]:
        """Return additional diagnostic evidence without modifying a device."""
        ...
