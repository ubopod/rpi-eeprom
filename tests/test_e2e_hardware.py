"""End-to-end hardware tests for EEPROM read/write on a real Raspberry Pi.

These tests interact with a physical EEPROM chip over I2C. They are skipped
automatically when no EEPROM is detected (i.e. on dev machines and in CI).

Run on a Raspberry Pi with an EEPROM attached::

    sudo pytest tests/test_e2e_hardware.py -v -m hardware

Prerequisites:
    - I2C overlay loaded: sudo dtoverlay i2c-gpio i2c_gpio_sda=0 i2c_gpio_scl=1 bus=9
    - eepmake, eepdump, eepflash.sh installed or bundled
    - gpiozero installed: pip install rpi-eeprom[gpio]
    - sudo access (eepflash.sh requires it)
"""

from __future__ import annotations

from collections.abc import Generator

import pytest

from rpi_eeprom import EEPROM, EEPROMConfig
from rpi_eeprom._gpio import MockWriteProtect
from rpi_eeprom._tools import detect_i2c

# Default hardware configuration — adjust if your setup differs
_HW_CONFIG = EEPROMConfig()


def _hardware_available() -> bool:
    """Check if an EEPROM is reachable on the default I2C bus."""
    try:
        return detect_i2c(_HW_CONFIG.i2c_bus, _HW_CONFIG.i2c_address)
    except Exception:
        return False


# Skip the entire module when no hardware is present
pytestmark = [
    pytest.mark.hardware,
    pytest.mark.skipif(
        not _hardware_available(),
        reason="No EEPROM detected — skipping hardware tests",
    ),
]


@pytest.fixture
def eeprom() -> Generator[EEPROM]:
    """Provide an EEPROM instance connected to real hardware."""
    with EEPROM(_HW_CONFIG) as e:
        if isinstance(e._write_protect, MockWriteProtect):
            pytest.fail(
                "gpiozero is not installed — write-protect pin cannot be "
                "toggled, so EEPROM writes will fail. "
                "Install with: pip install rpi-eeprom[gpio]"
            )
        yield e


class TestHardwareDetect:
    """Verify the device is actually detected."""

    def test_detect_returns_true(self, eeprom: EEPROM) -> None:
        assert eeprom.detect() is True


class TestHardwareReset:
    """Verify reset blanks the EEPROM."""

    def test_reset_blanks_eeprom(self, eeprom: EEPROM) -> None:
        eeprom.reset()
        # After reset, read should fail because there is no valid HAT data
        with pytest.raises(Exception):
            eeprom.read()


class TestHardwareWriteReadRoundTrip:
    """Write known data, read it back, and verify it matches."""

    def test_write_and_read_back(self, eeprom: EEPROM) -> None:
        test_serial = f"E2E{EEPROM.generate_serial_number(8)}"
        test_data = {
            "serial_number": test_serial,
            "test_marker": "e2e_hardware_test",
            "version": 1,
        }

        # Write
        eeprom.write(custom_data=[test_data])

        # Read back
        content = eeprom.read()

        # Validate
        assert content.serial_number == test_serial
        assert len(content.custom_data) == 1
        assert content.custom_data[0]["test_marker"] == "e2e_hardware_test"
        assert content.custom_data[0]["version"] == 1
        assert content.product_uuid != ""
        assert content.product_uuid != "00000000-0000-0000-0000-000000000000"

    def test_write_multiple_sections_and_read_back(
        self, eeprom: EEPROM,
    ) -> None:
        section_0 = {"serial_number": f"E2E{EEPROM.generate_serial_number(8)}"}
        section_1 = {"extra_key": "extra_value", "count": 42}

        eeprom.write(custom_data=[section_0, section_1])

        content = eeprom.read()
        assert len(content.custom_data) == 2
        assert content.custom_data[0]["serial_number"] == section_0["serial_number"]
        assert content.custom_data[1]["extra_key"] == "extra_value"
        assert content.custom_data[1]["count"] == 42


class TestHardwareUpdate:
    """Test update operations that preserve UUID while changing custom data."""

    def test_update_preserves_uuid(self, eeprom: EEPROM) -> None:
        # Initial write
        original_serial = f"E2E{EEPROM.generate_serial_number(8)}"
        eeprom.write(custom_data=[{"serial_number": original_serial}])
        original = eeprom.read()

        # Update with new custom data
        new_serial = f"E2E{EEPROM.generate_serial_number(8)}"
        eeprom.update(custom_data=[{"serial_number": new_serial}])
        updated = eeprom.read()

        # UUID should be preserved, serial should change
        assert updated.product_uuid == original.product_uuid
        assert updated.serial_number == new_serial
        assert updated.serial_number != original_serial

    def test_update_append(self, eeprom: EEPROM) -> None:
        # Initial write with one section
        serial = f"E2E{EEPROM.generate_serial_number(8)}"
        eeprom.write(custom_data=[{"serial_number": serial}])

        # Append a second section
        eeprom.update(custom_data=[{"appended": True}], append=True)
        content = eeprom.read()

        assert len(content.custom_data) == 2
        assert content.custom_data[0]["serial_number"] == serial
        assert content.custom_data[1]["appended"] is True


class TestHardwareFullCycle:
    """Full end-to-end cycle: detect -> write -> read -> update -> read -> reset."""

    def test_full_lifecycle(self, eeprom: EEPROM) -> None:
        # 1. Detect
        assert eeprom.detect() is True

        # 2. Write initial data
        serial = f"E2E{EEPROM.generate_serial_number(8)}"
        eeprom.write(custom_data=[{
            "serial_number": serial,
            "lifecycle_test": True,
        }])

        # 3. Read back and validate
        content = eeprom.read()
        assert content.serial_number == serial
        assert content.custom_data[0]["lifecycle_test"] is True
        original_uuid = content.product_uuid

        # 4. Update — replace custom data, UUID preserved
        new_serial = f"E2E{EEPROM.generate_serial_number(8)}"
        eeprom.update(custom_data=[{
            "serial_number": new_serial,
            "lifecycle_test": True,
            "updated": True,
        }])

        # 5. Read back updated content
        updated = eeprom.read()
        assert updated.product_uuid == original_uuid
        assert updated.serial_number == new_serial
        assert updated.custom_data[0]["updated"] is True

        # 6. Reset to blank
        eeprom.reset()

        # 7. Verify blank — read should fail on a blanked EEPROM
        with pytest.raises(Exception):
            eeprom.read()
