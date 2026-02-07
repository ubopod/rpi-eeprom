"""Shared test fixtures for rpi_eeprom tests."""

from __future__ import annotations

import pytest

from rpi_eeprom._config import EEPROMConfig


@pytest.fixture
def config() -> EEPROMConfig:
    """Create a default test configuration."""
    return EEPROMConfig()


@pytest.fixture
def custom_config() -> EEPROMConfig:
    """Create a custom test configuration."""
    return EEPROMConfig(
        model="24c64",
        size_kbytes=8,
        i2c_bus=1,
        i2c_address=0x51,
        write_protect_pin=17,
    )
