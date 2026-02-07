"""Command-line interface for EEPROM operations.

Provides subcommands for reading, writing, and resetting EEPROM content
on Raspberry Pi HAT devices.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import warnings
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

from rpi_eeprom import (
    EEPROM,
    EEPROMConfig,
    EEPROMError,
    EEPROMReadError,
)
from rpi_eeprom._serial import generate_serial_number

logger = logging.getLogger(__name__)

# Old config keys that are no longer used
_DEPRECATED_CONFIG_KEYS = {"tools_path", "files_path", "json_path"}


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()],
    )


def _load_config(config_path: Path) -> EEPROMConfig:
    """Load configuration from a JSON or YAML file."""
    with open(config_path) as f:
        content = f.read()

    # Try JSON first, then YAML
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError as e:
            raise SystemExit(f"Config file is neither valid JSON nor YAML: {e}")

    if not isinstance(data, dict):
        raise SystemExit("Config file must contain a mapping/object")

    # Warn about deprecated keys
    deprecated = _DEPRECATED_CONFIG_KEYS & set(data)
    if deprecated:
        for key in deprecated:
            warnings.warn(
                f"Config key '{key}' is deprecated and will be ignored. "
                "Tool paths and file paths are now managed automatically.",
                DeprecationWarning,
                stacklevel=2,
            )
            del data[key]

    # Convert string i2c_address to int if needed
    if "i2c_address" in data and isinstance(data["i2c_address"], str):
        try:
            data["i2c_address"] = int(data["i2c_address"], 16)
        except ValueError:
            raise SystemExit(f"Invalid i2c_address: {data['i2c_address']}")

    return EEPROMConfig(**data)


def _handle_existing_content(eeprom: EEPROM, force: bool = False) -> int:
    """Handle existing EEPROM content (moved from library to CLI).

    Checks the current state and takes appropriate action:
    - Blank EEPROM: performs a full write with new serial
    - Zero UUID: performs a full write
    - Valid content: reports it
    """
    try:
        content = eeprom.read()
    except EEPROMReadError:
        logger.info("EEPROM appears blank or unreadable, writing fresh content")
        return _write_fresh(eeprom)

    zero_uuid = "00000000-0000-0000-0000-000000000000"
    if not content.product_uuid or content.product_uuid == zero_uuid:
        logger.info("EEPROM has blank/zero UUID, writing fresh content")
        return _write_fresh(eeprom)

    if not content.custom_data or not isinstance(content.custom_data[0], dict):
        if not force:
            logger.error("Corrupt custom data. Use --force to overwrite.")
            return 1
        logger.info("Force flag set, writing fresh content")
        return _write_fresh(eeprom)

    serial = content.serial_number
    if serial:
        logger.info("Found existing serial number: %s", serial)
        return 0

    logger.info("No serial number found, writing fresh content")
    return _write_fresh(eeprom)


def _write_fresh(eeprom: EEPROM) -> int:
    """Write a fresh EEPROM image with a new serial number."""
    serial = generate_serial_number()
    logger.info("Generated new serial number: %s", serial)
    custom = {"serial_number": serial}
    try:
        eeprom.write(custom_data=[custom])
        logger.info("EEPROM written successfully")
        return 0
    except EEPROMError as e:
        logger.error("Failed to write EEPROM: %s", e)
        return 1


def _format_output(data: Any, fmt: str) -> str:
    if fmt == "yaml":
        result: str = yaml.dump(
            data, default_flow_style=False, sort_keys=True,
        )
        return result
    return json.dumps(data, indent=2, sort_keys=True)


def _cmd_read(args: argparse.Namespace, eeprom: EEPROM) -> int:
    """Handle the 'read' subcommand."""
    if args.device_tree:
        idx = args.index if args.index is not None else 0
        try:
            data: Any = eeprom.read_device_tree(idx)
        except FileNotFoundError:
            logger.error("Device tree entry not found (index %d)", idx)
            return 1
    else:
        try:
            content = eeprom.read()
        except EEPROMReadError as e:
            logger.error("Failed to read EEPROM: %s", e)
            return 1

        # Convert to a plain dict for output
        data = {
            "product_uuid": content.product_uuid,
            "product_id": content.product_id,
            "product_ver": content.product_ver,
            "vendor": content.vendor,
            "product": content.product,
            "custom_data": content.custom_data,
        }
        if content.dt_blob:
            data["dt_blob"] = content.dt_blob

        if args.index is not None:
            if args.index < 0 or args.index >= len(content.custom_data):
                logger.error(
                    "Invalid index %d. Must be 0-%d",
                    args.index,
                    len(content.custom_data) - 1,
                )
                return 1
            data = content.custom_data[args.index]

    # Determine output format
    fmt = getattr(args, "format", "json") or "json"
    if args.output:
        if args.output.suffix.lower() in (".yaml", ".yml"):
            fmt = "yaml"
        elif args.output.suffix.lower() == ".json":
            fmt = "json"

    formatted = _format_output(data, fmt)

    if args.output:
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(formatted)
            logger.info("Saved output to %s", args.output)
        except OSError as e:
            logger.error("Failed to write output file: %s", e)
            return 1

    print(formatted)
    return 0


def _cmd_write(args: argparse.Namespace, eeprom: EEPROM) -> int:
    """Handle the 'write' subcommand."""
    if args.data:
        paths = [Path(p) for p in args.data]

        # Validate files exist
        for p in paths:
            if not p.exists():
                logger.error("Data file not found: %s", p)
                return 1

        data_items: Sequence[Path | dict[str, Any]] = paths

        try:
            if args.index is not None:
                if len(paths) > 1:
                    logger.error("Cannot specify multiple data files with --index")
                    return 1
                eeprom.update(
                    custom_data=data_items,
                    index=args.index,
                )
            elif getattr(args, "append", False):
                eeprom.update(custom_data=data_items, append=True)
            else:
                eeprom.update(custom_data=data_items)
            logger.info("EEPROM updated successfully")
            return 0
        except EEPROMError as e:
            logger.error("Failed to update EEPROM: %s", e)
            return 1

    if args.serial:
        if not args.serial.strip():
            logger.error("Serial number cannot be empty")
            return 1
        try:
            eeprom.update(custom_data=[{"serial_number": args.serial}])
            logger.info("Serial number updated to: %s", args.serial)
            return 0
        except EEPROMError as e:
            logger.error("Failed to update serial number: %s", e)
            return 1

    # No data or serial specified — handle existing content
    return _handle_existing_content(eeprom, getattr(args, "force", False))


def _cmd_reset(args: argparse.Namespace, eeprom: EEPROM) -> int:
    """Handle the 'reset' subcommand."""
    try:
        eeprom.reset()
        logger.info("EEPROM reset successfully")
        return 0
    except EEPROMError as e:
        logger.error("Failed to reset EEPROM: %s", e)
        return 1


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="rpi-eeprom",
        description="Raspberry Pi EEPROM Management Tool",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Force operations even with existing content",
    )
    parser.add_argument(
        "--config", "-c", type=Path,
        help="Path to configuration file (JSON/YAML)",
    )

    sub = parser.add_subparsers(dest="command", help="Command")

    # Read
    rp = sub.add_parser("read", help="Read EEPROM content")
    rp.add_argument(
        "--format", "-f", choices=["json", "yaml"],
        default="json", help="Output format",
    )
    rp.add_argument(
        "--device-tree", "-d", action="store_true",
        help="Read from device tree",
    )
    rp.add_argument(
        "--output", "-o", type=Path, help="Save output to file",
    )
    rp.add_argument(
        "--index", "-i", type=int,
        help="Read specific custom data section",
    )

    # Write
    wp = sub.add_parser("write", help="Write to EEPROM")
    wp.add_argument(
        "--serial", "-s", type=str,
        help="Serial number to write",
    )
    wp.add_argument(
        "--data", "-d", type=Path, action="append",
        help="Data file(s) to write",
    )
    wp.add_argument(
        "--append", "-a", action="store_true",
        help="Append to existing custom data",
    )
    wp.add_argument(
        "--index", "-i", type=int,
        help="Replace section at index",
    )

    # Reset
    sub.add_parser("reset", help="Reset EEPROM to blank state")

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)

    if not args.command:
        parser.print_help()
        return 1

    try:
        config = _load_config(args.config) if args.config else None
    except SystemExit:
        raise
    except Exception as e:
        logger.error("Failed to load config: %s", e)
        return 1

    try:
        with EEPROM(config) as eeprom:
            if not eeprom.detect():
                # For read --device-tree, we don't need I2C detection
                if args.command == "read" and getattr(args, "device_tree", False):
                    pass
                else:
                    logger.error("No EEPROM device detected!")
                    return 1

            if args.command == "read":
                return _cmd_read(args, eeprom)
            elif args.command == "write":
                return _cmd_write(args, eeprom)
            elif args.command == "reset":
                return _cmd_reset(args, eeprom)
            else:
                parser.print_help()
                return 1

    except KeyboardInterrupt:
        logger.info("Operation interrupted by user")
        return 130
    except EEPROMError as e:
        logger.error("EEPROM error: %s", e)
        return 1
    except Exception as e:
        logger.error("Unexpected error: %s", e)
        if args.verbose:
            logger.exception("Details:")
        return 1


if __name__ == "__main__":
    sys.exit(main())
