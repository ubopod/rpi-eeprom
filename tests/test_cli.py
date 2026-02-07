"""Tests for the CLI module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from rpi_eeprom.cli._main import _load_config, main


class TestLoadConfig:
    def test_load_json_config(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "model": "24c64",
            "i2c_bus": 1,
            "i2c_address": 81,
        }))
        config = _load_config(config_file)
        assert config.model == "24c64"
        assert config.i2c_bus == 1
        assert config.i2c_address == 0x51

    def test_load_yaml_config(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.yaml"
        config_file.write_text("model: 24c64\ni2c_bus: 1\ni2c_address: 81\n")
        config = _load_config(config_file)
        assert config.model == "24c64"

    def test_deprecated_keys_warning(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "tools_path": "/usr/local/bin",
            "files_path": "./files",
            "json_path": "./json",
        }))
        with pytest.warns(DeprecationWarning):
            _load_config(config_file)

    def test_string_i2c_address_conversion(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"i2c_address": "0x51"}))
        config = _load_config(config_file)
        assert config.i2c_address == 0x51


class TestMainCLI:
    def test_no_command_shows_help(self) -> None:
        result = main([])
        assert result == 1

    @patch("rpi_eeprom.cli._main.EEPROM")
    def test_read_no_device(self, mock_eeprom_cls: MagicMock) -> None:
        mock_instance = MagicMock()
        mock_instance.detect.return_value = False
        mock_instance.__enter__ = MagicMock(return_value=mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=False)
        mock_eeprom_cls.return_value = mock_instance

        result = main(["read"])
        assert result == 1
