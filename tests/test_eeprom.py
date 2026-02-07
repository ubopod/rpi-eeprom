"""Tests for the main EEPROM class."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from rpi_eeprom._config import EEPROMConfig
from rpi_eeprom._eeprom import EEPROM, EEPROMContent
from rpi_eeprom._exceptions import (
    EEPROMNotFoundError,
    EEPROMReadError,
    EEPROMWriteError,
)


@pytest.fixture
def eeprom() -> EEPROM:
    """Create EEPROM instance with auto_detect disabled and fake tool paths."""
    e = EEPROM(auto_detect=False)
    # Force detected so methods don't raise EEPROMNotFoundError
    e._detected = True
    # Set fake tool paths so tool resolution doesn't fail during tests
    e._tools._resolved["eepmake"] = Path("/usr/local/bin/eepmake")
    e._tools._resolved["eepdump"] = Path("/usr/local/bin/eepdump")
    e._tools._resolved["eepflash.sh"] = Path("/usr/local/bin/eepflash.sh")
    return e


@pytest.fixture
def undetected_eeprom() -> EEPROM:
    """Create EEPROM instance that has not detected a device."""
    return EEPROM(auto_detect=False)


class TestEEPROMInit:
    def test_default_config(self) -> None:
        e = EEPROM(auto_detect=False)
        assert e.config.model == "24c32"
        assert e.config.i2c_bus == 9
        assert e.config.i2c_address == 0x50
        e.close()

    def test_custom_config(self) -> None:
        config = EEPROMConfig(model="24c64", i2c_bus=1)
        e = EEPROM(config, auto_detect=False)
        assert e.config.model == "24c64"
        assert e.config.i2c_bus == 1
        e.close()

    def test_context_manager(self) -> None:
        with EEPROM(auto_detect=False) as e:
            assert e.config.model == "24c32"


class TestEEPROMDetect:
    @patch("rpi_eeprom._eeprom.detect_i2c", return_value=True)
    def test_detect_found(self, mock_detect: MagicMock) -> None:
        with EEPROM(auto_detect=False) as e:
            assert e.detect() is True

    @patch("rpi_eeprom._eeprom.detect_i2c", return_value=False)
    def test_detect_not_found(self, mock_detect: MagicMock) -> None:
        with EEPROM(auto_detect=False) as e:
            assert e.detect() is False


class TestEEPROMNotDetected:
    def test_read_raises(self, undetected_eeprom: EEPROM) -> None:
        with pytest.raises(EEPROMNotFoundError):
            undetected_eeprom.read()

    def test_write_raises(self, undetected_eeprom: EEPROM) -> None:
        with pytest.raises(EEPROMNotFoundError):
            undetected_eeprom.write(custom_data=[{"key": "val"}])

    def test_update_raises(self, undetected_eeprom: EEPROM) -> None:
        with pytest.raises(EEPROMNotFoundError):
            undetected_eeprom.update(custom_data=[{"key": "val"}])

    def test_reset_raises(self, undetected_eeprom: EEPROM) -> None:
        with pytest.raises(EEPROMNotFoundError):
            undetected_eeprom.reset()


class TestEEPROMRead:
    @patch("rpi_eeprom._eeprom._run")
    def test_read_success(self, mock_run: MagicMock, eeprom: EEPROM) -> None:
        # Setup: create the dump file that parse_eeprom_dump will read
        dump_path = eeprom._workdir / "dump.txt"

        def side_effect(cmd: list[Any], **kwargs: Any) -> MagicMock:
            # When eepdump is called, create the dump file
            str_cmd = [str(c) for c in cmd]
            if any("eepdump" in str(c) for c in str_cmd):
                dump_path.write_text(
                    'product_uuid 12345678-1234-5678-1234-567812345678\n'
                    'product_id 0x1234\n'
                    'product_ver 0x1\n'
                    'vendor "Test Vendor"\n'
                    'product "Test Product"\n'
                    'custom_data "\n'
                    '{"serial_number": "ABC123"}\n'
                    '\\"\n'
                )
            return MagicMock()

        mock_run.side_effect = side_effect

        content = eeprom.read()
        assert isinstance(content, EEPROMContent)
        assert content.product_uuid == "12345678-1234-5678-1234-567812345678"
        assert content.vendor == "Test Vendor"
        assert content.serial_number == "ABC123"

    @patch("rpi_eeprom._eeprom._run")
    def test_read_failure(self, mock_run: MagicMock, eeprom: EEPROM) -> None:
        import subprocess

        mock_run.side_effect = subprocess.CalledProcessError(1, "cmd")
        with pytest.raises(EEPROMReadError):
            eeprom.read()


class TestEEPROMContent:
    def test_serial_number_present(self) -> None:
        content = EEPROMContent(
            product_uuid="test",
            custom_data=[{"serial_number": "ABC123"}],
        )
        assert content.serial_number == "ABC123"

    def test_serial_number_absent(self) -> None:
        content = EEPROMContent(product_uuid="test", custom_data=[{"key": "val"}])
        assert content.serial_number is None

    def test_serial_number_empty_custom_data(self) -> None:
        content = EEPROMContent(product_uuid="test")
        assert content.serial_number is None

    def test_frozen(self) -> None:
        content = EEPROMContent(product_uuid="test")
        with pytest.raises(AttributeError):
            content.product_uuid = "other"  # type: ignore[misc]


class TestEEPROMReset:
    @patch("rpi_eeprom._eeprom._run")
    def test_reset_success(self, mock_run: MagicMock, eeprom: EEPROM) -> None:
        def side_effect(cmd: list[Any], **kwargs: Any) -> MagicMock:
            str_cmd = [str(c) for c in cmd]
            # When eepflash reads back, create a blank file
            if any("eepflash" in str(c) for c in str_cmd) and "-r" in str_cmd:
                readback = eeprom._workdir / "blank_readback.eep"
                readback.write_bytes(b"\x00" * 4096)
            return MagicMock()

        mock_run.side_effect = side_effect
        eeprom.reset()  # Should not raise

    @patch("rpi_eeprom._eeprom._run")
    def test_reset_verification_failure(
        self, mock_run: MagicMock, eeprom: EEPROM,
    ) -> None:
        def side_effect(cmd: list[Any], **kwargs: Any) -> MagicMock:
            str_cmd = [str(c) for c in cmd]
            if any("eepflash" in str(c) for c in str_cmd) and "-r" in str_cmd:
                readback = eeprom._workdir / "blank_readback.eep"
                readback.write_bytes(b"\xff" * 4096)
            return MagicMock()

        mock_run.side_effect = side_effect
        with pytest.raises(EEPROMWriteError, match="not blank"):
            eeprom.reset()


class TestEEPROMGenerateSerialNumber:
    def test_static_method(self) -> None:
        serial = EEPROM.generate_serial_number()
        assert len(serial) == 12
        assert all(c in "ABCDEFGHJKLMNPQRSTUVWXYZ0123456789" for c in serial)

    def test_custom_length(self) -> None:
        serial = EEPROM.generate_serial_number(8)
        assert len(serial) == 8


class TestEEPROMReadDeviceTree:
    def test_read_device_tree_not_found(self) -> None:
        e = EEPROM(auto_detect=False)
        with pytest.raises(FileNotFoundError):
            e.read_device_tree(0)
        e.close()

    def test_read_device_tree_success(self, tmp_path: Path) -> None:
        # Create a fake device tree file
        dt_file = tmp_path / "custom_0"
        dt_file.write_text(json.dumps({"serial_number": "ABC123"}))

        e = EEPROM(auto_detect=False)
        with patch("rpi_eeprom._eeprom.Path") as mock_path:
            # We need to mock the Path constructor to return our temp file
            mock_path.return_value = dt_file
            # Directly call with a patched open to use our file
            with patch("builtins.open", return_value=open(dt_file)):
                data = e.read_device_tree(0)
                assert data["serial_number"] == "ABC123"
        e.close()


class TestEEPROMPrepareCustomDataFiles:
    def test_dict_input(self, eeprom: EEPROM) -> None:
        files = eeprom._prepare_custom_data_files([{"key": "value"}])
        assert len(files) == 1
        assert files[0].exists()
        content = json.loads(files[0].read_text())
        assert content["key"] == "value"

    def test_path_input(self, eeprom: EEPROM, tmp_path: Path) -> None:
        data_file = tmp_path / "data.json"
        data_file.write_text('{"key": "value"}')
        files = eeprom._prepare_custom_data_files([data_file])
        assert len(files) == 1
        assert files[0] == data_file

    def test_mixed_input(self, eeprom: EEPROM, tmp_path: Path) -> None:
        data_file = tmp_path / "data.json"
        data_file.write_text('{"file_key": "val"}')
        files = eeprom._prepare_custom_data_files([
            data_file,
            {"dict_key": "val"},
        ])
        assert len(files) == 2

    def test_invalid_type(self, eeprom: EEPROM) -> None:
        with pytest.raises(TypeError):
            eeprom._prepare_custom_data_files(["not a path or dict"])  # type: ignore[list-item]
