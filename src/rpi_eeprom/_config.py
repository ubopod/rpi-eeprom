"""EEPROM configuration dataclass."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rpi_eeprom._exceptions import EEPROMConfigError


@dataclass(frozen=True)
class EEPROMConfig:
    """Configuration for EEPROM operations.

    All fields have sensible defaults for a typical Raspberry Pi HAT EEPROM
    setup using a 24c32 chip on I2C bus 9 at address 0x50.
    """

    model: str = "24c32"
    size_kbytes: int = 4
    i2c_bus: int = 9
    i2c_address: int = 0x50
    write_protect_pin: int = 16
    settings_template: str | Path | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.i2c_bus, int) or self.i2c_bus < 0:
            raise EEPROMConfigError(f"Invalid I2C bus number: {self.i2c_bus}")
        addr = self.i2c_address
        if not isinstance(addr, int) or not (0x00 <= addr <= 0x7F):
            raise EEPROMConfigError(
                f"Invalid I2C address: {self.i2c_address:#x}. Must be 0x00-0x7F."
            )
        if not isinstance(self.size_kbytes, int) or self.size_kbytes <= 0:
            raise EEPROMConfigError(f"Invalid EEPROM size: {self.size_kbytes}")
