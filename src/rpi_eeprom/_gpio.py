"""GPIO write-protect abstraction for EEPROM operations."""

from __future__ import annotations

import logging
import os
import platform
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class WriteProtect(Protocol):
    """Protocol for EEPROM write-protect pin control."""

    def enable(self) -> None:
        """Enable write protection (pin HIGH)."""
        ...

    def disable(self) -> None:
        """Disable write protection (pin LOW)."""
        ...

    def close(self) -> None:
        """Release underlying resources (e.g. GPIO pin reservation)."""
        ...


class GPIOWriteProtect:
    """Real GPIO write-protect using gpiozero."""

    def __init__(self, pin: int) -> None:
        from gpiozero import DigitalOutputDevice  # type: ignore[import-not-found]

        self._device = DigitalOutputDevice(pin)

    def enable(self) -> None:
        self._device.on()

    def disable(self) -> None:
        self._device.off()

    def close(self) -> None:
        self._device.close()


class MockWriteProtect:
    """Mock write-protect for non-RPi platforms or testing."""

    def __init__(self, pin: int) -> None:
        self.pin = pin
        self._enabled = False
        logger.debug("Initialized mock write-protect on pin %d", pin)

    def enable(self) -> None:
        self._enabled = True
        logger.debug("Mock write-protect enabled (pin %d)", self.pin)

    def disable(self) -> None:
        self._enabled = False
        logger.debug("Mock write-protect disabled (pin %d)", self.pin)

    def close(self) -> None:
        self._enabled = False


def _is_raspberry_pi() -> bool:
    """Detect if running on a Raspberry Pi."""
    return platform.system() == "Linux" and os.path.exists("/proc/device-tree/model")


def create_write_protect(pin: int) -> WriteProtect:
    """Create a write-protect controller appropriate for the current platform.

    On Raspberry Pi with gpiozero available, returns a real GPIO controller.
    Otherwise falls back to a mock implementation.
    """
    if _is_raspberry_pi():
        try:
            return GPIOWriteProtect(pin)
        except ImportError:
            logger.warning("gpiozero not available, using mock write-protect")
    else:
        logger.info("Non-Raspberry Pi platform detected, using mock write-protect")
    return MockWriteProtect(pin)
