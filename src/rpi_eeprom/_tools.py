"""Tool path resolution and subprocess wrappers for EEPROM operations."""

from __future__ import annotations

import importlib.resources
import logging
import os
import shutil
import subprocess
from contextlib import ExitStack
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class _ToolPaths:
    """Resolves paths to bundled EEPROM tool binaries.

    Uses importlib.resources to locate binaries shipped inside the package.
    Falls back to system-installed tools if bundled binaries are not available.
    """

    def __init__(self) -> None:
        self._exit_stack = ExitStack()
        self._resolved: dict[str, Path] = {}

    def _resolve(self, name: str) -> Path:
        if name in self._resolved:
            return self._resolved[name]

        # Try bundled binary first
        try:
            ref = importlib.resources.files("rpi_eeprom._vendor") / "bin" / name
            path = self._exit_stack.enter_context(importlib.resources.as_file(ref))
            if path.exists():
                os.chmod(path, 0o755)
                self._resolved[name] = path
                return path
        except (FileNotFoundError, TypeError):
            pass

        # Fall back to system PATH
        system_path = shutil.which(name)
        if system_path:
            resolved = Path(system_path)
            self._resolved[name] = resolved
            return resolved

        # Fall back to /usr/local/bin
        fallback = Path("/usr/local/bin") / name
        if fallback.exists():
            self._resolved[name] = fallback
            return fallback

        msg = (
            f"Tool '{name}' not found. Install it from "
            "https://github.com/raspberrypi/utils (eeptools) "
            "or reinstall rpi-eeprom with bundled binaries."
        )
        raise FileNotFoundError(msg)

    @property
    def eepmake(self) -> Path:
        return self._resolve("eepmake")

    @property
    def eepdump(self) -> Path:
        return self._resolve("eepdump")

    @property
    def eepflash(self) -> Path:
        return self._resolve("eepflash.sh")

    def close(self) -> None:
        self._exit_stack.close()


def _run(cmd: list[str | Path], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    """Run a subprocess command with logging.

    Raises:
        subprocess.CalledProcessError: If the command fails.
    """
    str_cmd = [str(c) for c in cmd]
    logger.debug("Running: %s", " ".join(str_cmd))
    try:
        return subprocess.run(
            str_cmd,
            capture_output=True,
            text=True,
            check=True,
            **kwargs,
        )
    except subprocess.CalledProcessError as e:
        logger.error("Command failed: %s", " ".join(str_cmd))
        logger.error("stderr: %s", e.stderr)
        raise


def detect_i2c(bus: int, address: int) -> bool:
    """Detect if an I2C device is present at the given bus and address.

    Parses the output of ``i2cdetect -y <bus>``. A device is present if its
    hex address appears as a value in the data columns (not as a row label).

    Returns True if the device responds, False otherwise.
    """
    addr_hex = f"{address:02x}"
    try:
        result = _run(["i2cdetect", "-y", str(bus)])
        for line in result.stdout.splitlines():
            # Skip header line and empty lines
            if not line or line[0] == " ":
                continue
            # Lines look like: "50: 50 -- -- -- ..."
            # Split on ":" to separate row label from values
            parts = line.split(":", 1)
            if len(parts) < 2:
                continue
            # Check if our address appears as a detected device in the values
            values = parts[1].split()
            if addr_hex in values:
                return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return False


def _eepflash_cmd(
    tools: _ToolPaths,
    mode: str,
    bus: int,
    address: int,
    filepath: Path,
    model: str,
) -> list[str | Path]:
    """Build an eepflash.sh command list."""
    addr_hex = f"{address:02x}"
    return [
        "sudo",
        tools.eepflash,
        f"-{mode}",
        f"-d={bus}",
        f"-a={addr_hex}",
        f"-f={filepath}",
        "-y",
        f"-t={model}",
    ]


def _resolve_settings_template(config_override: str | Path | None) -> Path:
    """Resolve the settings template path.

    Uses the user-provided path if given, otherwise falls back to
    the bundled default template.
    """
    if config_override is not None:
        path = Path(config_override)
        if not path.exists():
            raise FileNotFoundError(f"Settings template not found: {path}")
        return path

    pkg = importlib.resources.files("rpi_eeprom._vendor")
    ref = pkg / "templates" / "eeprom_settings.txt"
    # For the bundled template, we need to check if it exists
    try:
        with importlib.resources.as_file(ref) as path:
            if path.exists():
                return path
    except (FileNotFoundError, TypeError):
        pass

    raise FileNotFoundError(
        "No settings template found. Provide one via "
        "EEPROMConfig(settings_template=...) or ensure the bundled "
        "template is installed."
    )
