"""Raspberry Pi EEPROM management library.

Provides tools for reading, writing, and managing EEPROM content
on Raspberry Pi HAT devices.

Basic usage::

    from rpi_eeprom import EEPROM, EEPROMConfig

    with EEPROM() as eeprom:
        content = eeprom.read()
        print(content.serial_number)
"""

from __future__ import annotations

from rpi_eeprom._config import EEPROMConfig
from rpi_eeprom._eeprom import EEPROM, EEPROMContent
from rpi_eeprom._exceptions import (
    EEPROMConfigError,
    EEPROMError,
    EEPROMNotFoundError,
    EEPROMReadError,
    EEPROMWriteError,
)

__all__ = [
    "EEPROM",
    "EEPROMConfig",
    "EEPROMConfigError",
    "EEPROMContent",
    "EEPROMError",
    "EEPROMNotFoundError",
    "EEPROMReadError",
    "EEPROMWriteError",
]

__version__ = "1.1.0"
