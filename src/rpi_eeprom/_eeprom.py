"""Core EEPROM class for reading, writing, and managing HAT EEPROM content."""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rpi_eeprom._config import EEPROMConfig
from rpi_eeprom._exceptions import (
    EEPROMNotFoundError,
    EEPROMReadError,
    EEPROMWriteError,
)
from rpi_eeprom._gpio import WriteProtect, create_write_protect
from rpi_eeprom._parser import parse_eeprom_dump
from rpi_eeprom._serial import generate_serial_number
from rpi_eeprom._tools import (
    _eepflash_cmd,
    _resolve_settings_template,
    _run,
    _ToolPaths,
    detect_i2c,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EEPROMContent:
    """Parsed content read from an EEPROM device."""

    product_uuid: str = ""
    product_id: str = ""
    product_ver: str = ""
    vendor: str = ""
    product: str = ""
    dt_blob: str | None = None
    custom_data: list[dict[str, Any]] = field(default_factory=list)

    @property
    def serial_number(self) -> str | None:
        """Extract serial number from the first custom data section."""
        if self.custom_data and isinstance(self.custom_data[0], dict):
            return self.custom_data[0].get("serial_number")
        return None


class EEPROM:
    """Manage EEPROM operations on Raspberry Pi HAT devices.

    Supports reading, writing, updating, and resetting EEPROM content.
    Uses external tools (eepmake, eepdump, eepflash.sh) for hardware operations.

    Can be used as a context manager::

        with EEPROM() as eeprom:
            content = eeprom.read()
            print(content.serial_number)
    """

    def __init__(
        self,
        config: EEPROMConfig | None = None,
        *,
        auto_detect: bool = True,
    ) -> None:
        self._config = config or EEPROMConfig()
        self._tools = _ToolPaths()
        self._tmpdir = tempfile.TemporaryDirectory(prefix="rpi_eeprom_")
        self._workdir = Path(self._tmpdir.name)
        self._write_protect: WriteProtect = create_write_protect(
            self._config.write_protect_pin
        )
        self._detected: bool | None = None
        if auto_detect:
            self._detected = detect_i2c(self._config.i2c_bus, self._config.i2c_address)

    @property
    def config(self) -> EEPROMConfig:
        return self._config

    def __enter__(self) -> EEPROM:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        """Clean up temporary files, tool resources, and GPIO pins."""
        self._write_protect.close()
        self._tools.close()
        self._tmpdir.cleanup()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    # ---- Public API ----

    def detect(self) -> bool:
        """Check if an EEPROM device is present on the configured I2C bus.

        Returns:
            True if a device is detected.
        """
        result = detect_i2c(self._config.i2c_bus, self._config.i2c_address)
        self._detected = result
        return result

    def read(self) -> EEPROMContent:
        """Read and parse all EEPROM content.

        Reads raw binary from the hardware, converts to text via eepdump,
        then parses into an EEPROMContent dataclass.

        Raises:
            EEPROMNotFoundError: If no device is detected.
            EEPROMReadError: If the read or parse operation fails.
        """
        self._require_detected()

        readback = self._workdir / "readback.eep"
        dump = self._workdir / "dump.txt"

        try:
            self._eepflash_read(readback)
            _run([self._tools.eepdump, readback, dump])
            info = parse_eeprom_dump(dump)
        except (subprocess.CalledProcessError, OSError) as e:
            raise EEPROMReadError(f"Failed to read EEPROM: {e}") from e

        custom_data_all = info.get("custom_data_all", [])

        return EEPROMContent(
            product_uuid=info.get("product_uuid", ""),
            product_id=info.get("product_id", ""),
            product_ver=info.get("product_ver", ""),
            vendor=info.get("vendor", ""),
            product=info.get("product", ""),
            dt_blob=info.get("dt_blob"),
            custom_data=custom_data_all,
        )

    def read_device_tree(self, index: int = 0) -> dict[str, Any]:
        """Read EEPROM data from the Linux device tree.

        This reads how the system currently sees the EEPROM content through
        ``/proc/device-tree/hat/custom_N``. Changes to the EEPROM are not
        reflected until a reboot.

        Args:
            index: Custom data section index (default: 0).

        Raises:
            FileNotFoundError: If the device tree entry does not exist.
        """
        path = Path(f"/proc/device-tree/hat/custom_{index}")
        with open(path) as f:
            data: dict[str, Any] = json.load(f)
        return data

    def write(
        self,
        custom_data: Sequence[Path | dict[str, Any]],
        *,
        settings_template: str | Path | None = None,
    ) -> None:
        """Write new content to the EEPROM (full reset + write).

        This resets the EEPROM, then writes a new image built from the
        settings template and custom data sections.

        Args:
            custom_data: List of custom data sections. Each can be a Path to
                a JSON/YAML file or a dict that will be serialized to JSON.
            settings_template: Optional path to a settings template file.
                Falls back to EEPROMConfig.settings_template, then to bundled default.

        Raises:
            EEPROMNotFoundError: If no device is detected.
            EEPROMWriteError: If the write or verification fails.
        """
        self._require_detected()

        template = _resolve_settings_template(
            settings_template or self._config.settings_template
        )
        data_files = self._prepare_custom_data_files(custom_data)

        try:
            self._write_protect.disable()
            try:
                self._blank_and_verify()
                image = self._make_image(template, data_files)
                self._eepflash_write(image)
            finally:
                self._write_protect.enable()
            logger.info("EEPROM write completed successfully")
        except EEPROMWriteError:
            raise
        except (subprocess.CalledProcessError, OSError) as e:
            raise EEPROMWriteError(f"Failed to write EEPROM: {e}") from e

    def update(
        self,
        custom_data: Sequence[Path | dict[str, Any]],
        *,
        append: bool = False,
        index: int | None = None,
    ) -> None:
        """Update EEPROM custom data while preserving UUID and settings.

        Reads the current content, modifies the custom data sections,
        then writes the updated image.

        Args:
            custom_data: New custom data sections (Paths or dicts).
            append: If True, append to existing sections. If False, replace all.
            index: If set, replace only the section at this index.

        Raises:
            EEPROMNotFoundError: If no device is detected.
            EEPROMReadError: If the current content cannot be read.
            EEPROMWriteError: If the write fails.
        """
        self._require_detected()

        # Read current content to get the dump
        readback = self._workdir / "readback.eep"
        dump = self._workdir / "dump.txt"

        try:
            self._eepflash_read(readback)
            _run([self._tools.eepdump, readback, dump])
            info = parse_eeprom_dump(dump)
        except (subprocess.CalledProcessError, OSError) as e:
            raise EEPROMReadError(f"Failed to read current EEPROM: {e}") from e

        existing_sections = info.get("custom_data_all", [])
        new_files = self._prepare_custom_data_files(custom_data)

        if index is not None:
            # Replace a specific section
            if index < 0 or index >= len(existing_sections):
                raise EEPROMWriteError(
                    f"Invalid index {index}. "
                    f"Must be 0-{len(existing_sections) - 1}."
                )
            all_files = self._prepare_existing_sections(existing_sections)
            all_files[index] = new_files[0]
            data_files = all_files
        elif append:
            # Append new sections after existing
            existing_files = self._prepare_existing_sections(existing_sections)
            data_files = existing_files + new_files
        else:
            # Replace all custom data
            data_files = new_files

        # Strip custom data from the dump and rebuild
        stripped_dump = self._strip_custom_data(dump)

        try:
            image = self._make_image(stripped_dump, data_files)
            self._write_protect.disable()
            try:
                self._blank_and_verify()
                self._eepflash_write(image)
            finally:
                self._write_protect.enable()
            logger.info("EEPROM update completed successfully")
        except EEPROMWriteError:
            raise
        except (subprocess.CalledProcessError, OSError) as e:
            raise EEPROMWriteError(f"Failed to update EEPROM: {e}") from e

    def reset(self) -> None:
        """Reset EEPROM to a blank state and verify.

        Raises:
            EEPROMNotFoundError: If no device is detected.
            EEPROMWriteError: If the reset or verification fails.
        """
        self._require_detected()

        try:
            self._write_protect.disable()
            try:
                self._blank_and_verify()
            finally:
                self._write_protect.enable()
        except EEPROMWriteError:
            raise
        except (subprocess.CalledProcessError, OSError) as e:
            raise EEPROMWriteError(f"Failed to reset EEPROM: {e}") from e

    def _blank_and_verify(self) -> None:
        """Write zeros to the EEPROM and verify. Caller must manage write-protect."""
        blank = self._workdir / "blank.eep"
        blank_readback = self._workdir / "blank_readback.eep"

        # Create blank binary
        blank.write_bytes(b"\x00" * (self._config.size_kbytes * 1024))

        # Write blank to EEPROM
        self._eepflash_write(blank)
        time.sleep(0.5)

        # Read back and verify
        self._eepflash_read(blank_readback)
        content = blank_readback.read_bytes()
        if any(byte != 0 for byte in content):
            raise EEPROMWriteError("EEPROM verification failed — not blank")

        logger.info("EEPROM successfully blanked and verified")

    @staticmethod
    def generate_serial_number(length: int = 12) -> str:
        """Generate a random serial number.

        Wraps :func:`rpi_eeprom._serial.generate_serial_number`.
        """
        return generate_serial_number(length)

    # ---- Internal helpers ----

    def _require_detected(self) -> None:
        """Raise if no EEPROM has been detected."""
        if not self._detected:
            raise EEPROMNotFoundError(
                f"No EEPROM detected on I2C bus {self._config.i2c_bus} "
                f"at address {self._config.i2c_address:#x}"
            )

    def _eepflash_read(self, output: Path) -> None:
        """Read raw EEPROM content via eepflash.sh."""
        cmd = _eepflash_cmd(
            self._tools, "r", self._config.i2c_bus,
            self._config.i2c_address, output, self._config.model,
        )
        _run(cmd)

    def _eepflash_write(self, image: Path) -> None:
        """Write a binary image to the EEPROM via eepflash.sh."""
        cmd = _eepflash_cmd(
            self._tools, "w", self._config.i2c_bus,
            self._config.i2c_address, image, self._config.model,
        )
        _run(cmd)

    def _make_image(
        self,
        template: Path,
        data_files: list[Path],
    ) -> Path:
        """Create an EEPROM binary image from a template and custom data files."""
        image = self._workdir / "image.eep"
        cmd: list[str | Path] = [self._tools.eepmake, "-v1", template, image]
        if data_files:
            cmd.append("-c")
            cmd.extend(data_files)
        _run(cmd)
        return image

    def _prepare_custom_data_files(
        self, custom_data: Sequence[Path | dict[str, Any]]
    ) -> list[Path]:
        """Convert custom data items (Paths or dicts) to file paths."""
        result: list[Path] = []
        for i, item in enumerate(custom_data):
            if isinstance(item, Path):
                result.append(item)
            elif isinstance(item, dict):
                tmp = self._workdir / f"custom_data_{i}.json"
                tmp.write_text(json.dumps(item))
                result.append(tmp)
            else:
                raise TypeError(f"Expected Path or dict, got {type(item)}")
        return result

    def _prepare_existing_sections(
        self, sections: list[Any]
    ) -> list[Path]:
        """Serialize existing custom data sections to temporary files."""
        result: list[Path] = []
        for i, section in enumerate(sections):
            tmp = self._workdir / f"existing_{i}.json"
            if isinstance(section, dict):
                tmp.write_text(json.dumps(section))
            else:
                tmp.write_text(json.dumps({"data": section}))
            result.append(tmp)
        return result

    def _strip_custom_data(self, dump_path: Path) -> Path:
        """Remove custom_data sections from an EEPROM dump file.

        Returns a new file path with the stripped content.
        """
        stripped = self._workdir / "stripped_dump.txt"
        with open(dump_path) as src, open(stripped, "w") as dst:
            for line in src:
                if "Start of atom #2" in line or "Start of atom #3" in line:
                    break
                dst.write(line)
        return stripped
