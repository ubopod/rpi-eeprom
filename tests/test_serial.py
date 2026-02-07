"""Tests for serial number generation."""

from __future__ import annotations

from rpi_eeprom._serial import generate_serial_number

_CHARSET = "ABCDEFGHJKLMNPQRSTUVWXYZ0123456789"


class TestGenerateSerialNumber:
    def test_default_length(self) -> None:
        serial = generate_serial_number()
        assert len(serial) == 12

    def test_custom_length(self) -> None:
        serial = generate_serial_number(length=8)
        assert len(serial) == 8

    def test_valid_characters(self) -> None:
        serial = generate_serial_number()
        assert all(c in _CHARSET for c in serial)

    def test_no_ambiguous_characters(self) -> None:
        # Generate many to increase probability of catching errors
        for _ in range(100):
            serial = generate_serial_number()
            assert "I" not in serial
            assert "O" not in serial

    def test_uniqueness(self) -> None:
        serials = {generate_serial_number() for _ in range(100)}
        # With 34^12 possibilities, collisions are astronomically unlikely
        assert len(serials) == 100
