"""Exception hierarchy for EEPROM operations."""

from __future__ import annotations


class EEPROMError(Exception):
    """Base exception for EEPROM operations."""


class EEPROMConfigError(EEPROMError):
    """Exception raised when configuration is invalid."""


class EEPROMNotFoundError(EEPROMError):
    """Exception raised when EEPROM is not detected."""


class EEPROMWriteError(EEPROMError):
    """Exception raised when writing to EEPROM fails."""


class EEPROMReadError(EEPROMError):
    """Exception raised when reading from EEPROM fails."""
