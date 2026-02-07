"""Tests for tool path resolution and subprocess wrappers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from rpi_eeprom._tools import (
    _eepflash_cmd,
    _run,
    _ToolPaths,
    detect_i2c,
)


class TestRun:
    def test_successful_command(self) -> None:
        result = _run(["echo", "hello"])
        assert result.stdout.strip() == "hello"

    def test_failed_command(self) -> None:
        import subprocess

        with pytest.raises(subprocess.CalledProcessError):
            _run(["false"])

    def test_path_arguments(self, tmp_path: Path) -> None:
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")
        result = _run(["cat", test_file])
        assert result.stdout == "content"


class TestDetectI2C:
    @patch("rpi_eeprom._tools._run")
    def test_device_found(self, mock_run: object) -> None:
        from unittest.mock import MagicMock

        mock_result = MagicMock()
        header = "     0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f"
        mock_result.stdout = (
            f"{header}\n"
            "50: 50 -- -- -- -- -- -- -- -- -- -- -- -- -- -- --\n"
        )
        assert isinstance(mock_run, MagicMock)
        mock_run.return_value = mock_result
        assert detect_i2c(9, 0x50) is True

    @patch("rpi_eeprom._tools._run")
    def test_device_not_found(self, mock_run: object) -> None:
        from unittest.mock import MagicMock

        mock_result = MagicMock()
        header = "     0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f"
        mock_result.stdout = (
            f"{header}\n"
            "50: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --\n"
        )
        assert isinstance(mock_run, MagicMock)
        mock_run.return_value = mock_result
        assert detect_i2c(9, 0x50) is False

    @patch("rpi_eeprom._tools._run")
    def test_i2cdetect_not_found(self, mock_run: object) -> None:
        from unittest.mock import MagicMock

        assert isinstance(mock_run, MagicMock)
        mock_run.side_effect = FileNotFoundError
        assert detect_i2c(9, 0x50) is False


class TestEepflashCmd:
    def test_read_command(self) -> None:
        tools = _ToolPaths()
        # Manually set a fake path for eepflash
        tools._resolved["eepflash.sh"] = Path("/usr/local/bin/eepflash.sh")
        cmd = _eepflash_cmd(tools, "r", 9, 0x50, Path("/tmp/out.eep"), "24c32")
        assert cmd[0] == "sudo"
        assert cmd[1] == Path("/usr/local/bin/eepflash.sh")
        assert "-r" in cmd
        assert "-d=9" in cmd
        assert "-a=50" in cmd
        assert "-f=/tmp/out.eep" in cmd
        assert "-t=24c32" in cmd
        tools.close()

    def test_write_command(self) -> None:
        tools = _ToolPaths()
        tools._resolved["eepflash.sh"] = Path("/usr/local/bin/eepflash.sh")
        cmd = _eepflash_cmd(tools, "w", 1, 0x51, Path("/tmp/in.eep"), "24c64")
        assert "-w" in cmd
        assert "-d=1" in cmd
        assert "-a=51" in cmd
        tools.close()


class TestToolPaths:
    def test_close_is_idempotent(self) -> None:
        tools = _ToolPaths()
        tools.close()
        tools.close()  # Should not raise
