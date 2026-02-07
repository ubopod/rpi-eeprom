"""Tests for GPIO write-protect abstraction."""

from __future__ import annotations

from rpi_eeprom._gpio import MockWriteProtect, WriteProtect, create_write_protect


class TestMockWriteProtect:
    def test_initial_state(self) -> None:
        wp = MockWriteProtect(pin=16)
        assert wp._enabled is False

    def test_enable(self) -> None:
        wp = MockWriteProtect(pin=16)
        wp.enable()
        assert wp._enabled is True

    def test_disable(self) -> None:
        wp = MockWriteProtect(pin=16)
        wp.enable()
        wp.disable()
        assert wp._enabled is False

    def test_implements_protocol(self) -> None:
        wp = MockWriteProtect(pin=16)
        assert isinstance(wp, WriteProtect)


class TestCreateWriteProtect:
    def test_non_rpi_returns_mock(self) -> None:
        # On macOS/non-RPi, should return mock
        wp = create_write_protect(16)
        assert isinstance(wp, MockWriteProtect)
