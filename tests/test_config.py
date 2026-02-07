"""Tests for EEPROMConfig dataclass."""

from __future__ import annotations

from pathlib import Path

import pytest

from rpi_eeprom._config import EEPROMConfig
from rpi_eeprom._exceptions import EEPROMConfigError


class TestEEPROMConfigDefaults:
    def test_default_values(self) -> None:
        config = EEPROMConfig()
        assert config.model == "24c32"
        assert config.size_kbytes == 4
        assert config.i2c_bus == 9
        assert config.i2c_address == 0x50
        assert config.write_protect_pin == 16
        assert config.settings_template is None

    def test_frozen(self) -> None:
        config = EEPROMConfig()
        with pytest.raises(AttributeError):
            config.model = "24c64"  # type: ignore[misc]


class TestEEPROMConfigCustom:
    def test_custom_values(self) -> None:
        config = EEPROMConfig(
            model="24c64",
            size_kbytes=8,
            i2c_bus=1,
            i2c_address=0x51,
            write_protect_pin=17,
            settings_template=Path("/tmp/test.txt"),
        )
        assert config.model == "24c64"
        assert config.size_kbytes == 8
        assert config.i2c_bus == 1
        assert config.i2c_address == 0x51
        assert config.write_protect_pin == 17
        assert config.settings_template == Path("/tmp/test.txt")

    def test_settings_template_string(self) -> None:
        config = EEPROMConfig(settings_template="/tmp/test.txt")
        assert config.settings_template == "/tmp/test.txt"


class TestEEPROMConfigValidation:
    def test_negative_bus(self) -> None:
        with pytest.raises(EEPROMConfigError, match="Invalid I2C bus"):
            EEPROMConfig(i2c_bus=-1)

    def test_address_too_high(self) -> None:
        with pytest.raises(EEPROMConfigError, match="Invalid I2C address"):
            EEPROMConfig(i2c_address=0x80)

    def test_address_too_low_is_valid(self) -> None:
        # Address 0x00 is technically valid (general call)
        config = EEPROMConfig(i2c_address=0x00)
        assert config.i2c_address == 0x00

    def test_zero_size(self) -> None:
        with pytest.raises(EEPROMConfigError, match="Invalid EEPROM size"):
            EEPROMConfig(size_kbytes=0)

    def test_negative_size(self) -> None:
        with pytest.raises(EEPROMConfigError, match="Invalid EEPROM size"):
            EEPROMConfig(size_kbytes=-1)
