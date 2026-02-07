"""Tests for EEPROM dump parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from rpi_eeprom._parser import parse_eeprom_dump


@pytest.fixture
def dump_dir(tmp_path: Path) -> Path:
    return tmp_path


class TestParseEepromDump:
    def test_parse_full_dump(self, dump_dir: Path) -> None:
        dump = dump_dir / "dump.txt"
        dump.write_text(
            'product_uuid 12345678-1234-5678-1234-567812345678\n'
            'product_id 0x1234\n'
            'product_ver 0x1\n'
            'vendor "Test Vendor"\n'
            'product "Test Product"\n'
            'dt_blob "test_blob"\n'
            'custom_data "\n'
            '{"serial_number": "ABC123"}\n'
            '\\"\n'
        )
        info = parse_eeprom_dump(dump)
        assert info["product_uuid"] == "12345678-1234-5678-1234-567812345678"
        assert info["product_id"] == "0x1234"
        assert info["product_ver"] == "0x1"
        assert info["vendor"] == "Test Vendor"
        assert info["product"] == "Test Product"
        assert info["dt_blob"] == "test_blob"
        assert len(info["custom_data_all"]) == 1
        assert info["custom_data_all"][0]["serial_number"] == "ABC123"

    def test_parse_multiple_custom_data(self, dump_dir: Path) -> None:
        dump = dump_dir / "dump.txt"
        dump.write_text(
            'product_uuid 12345678-1234-5678-1234-567812345678\n'
            'custom_data "\n'
            '{"serial_number": "ABC123"}\n'
            '\\"\n'
            'custom_data "\n'
            '{"key": "value"}\n'
            '\\"\n'
        )
        info = parse_eeprom_dump(dump)
        assert len(info["custom_data_all"]) == 2
        assert info["custom_data_all"][0]["serial_number"] == "ABC123"
        assert info["custom_data_all"][1]["key"] == "value"

    def test_parse_yaml_custom_data(self, dump_dir: Path) -> None:
        dump = dump_dir / "dump.txt"
        dump.write_text(
            'product_uuid 12345678-1234-5678-1234-567812345678\n'
            'custom_data "\n'
            'serial_number: XYZ789\n'
            '\\"\n'
        )
        info = parse_eeprom_dump(dump)
        assert len(info["custom_data_all"]) == 1
        assert info["custom_data_all"][0]["serial_number"] == "XYZ789"

    def test_parse_empty_file(self, dump_dir: Path) -> None:
        dump = dump_dir / "dump.txt"
        dump.write_text("")
        info = parse_eeprom_dump(dump)
        assert info == {}

    def test_parse_no_custom_data(self, dump_dir: Path) -> None:
        dump = dump_dir / "dump.txt"
        dump.write_text(
            'product_uuid 12345678-1234-5678-1234-567812345678\n'
            'product_id 0x1234\n'
        )
        info = parse_eeprom_dump(dump)
        assert info["product_uuid"] == "12345678-1234-5678-1234-567812345678"
        assert "custom_data_all" not in info

    def test_file_not_found(self, dump_dir: Path) -> None:
        with pytest.raises(FileNotFoundError):
            parse_eeprom_dump(dump_dir / "nonexistent.txt")

    def test_unparseable_custom_data_stored_as_string(self, dump_dir: Path) -> None:
        dump = dump_dir / "dump.txt"
        dump.write_text(
            'product_uuid test-uuid\n'
            'custom_data "\n'
            'this is not json or yaml: [[[invalid\n'
            '\\"\n'
        )
        info = parse_eeprom_dump(dump)
        assert len(info["custom_data_all"]) == 1
        assert isinstance(info["custom_data_all"][0], str)
