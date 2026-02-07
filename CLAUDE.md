# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Raspberry Pi EEPROM management tool for reading, writing, and managing EEPROM content on RPi HAT devices. Installable via `pip install rpi-eeprom`. Provides a Python library (`rpi_eeprom`) and CLI (`rpi-eeprom`). Supports JSON and YAML custom data formats with multi-section storage.

## Commands

```bash
# Install in development mode
pip install -e ".[dev]"

# Run all tests
pytest tests/ -v

# Run a specific test
pytest tests/ -v -k "test_generate_serial_number"

# Run with coverage
pytest tests/ -v --cov=rpi_eeprom

# Lint
ruff check src/ tests/

# Type check
mypy src/rpi_eeprom/

# CLI help
rpi-eeprom --help
```

## Architecture

The package lives under `src/rpi_eeprom/` using the src layout with hatchling as the build backend.

### Core modules

- **`_exceptions.py`** — Exception hierarchy: `EEPROMError` -> `EEPROMConfigError`, `EEPROMNotFoundError`, `EEPROMWriteError`, `EEPROMReadError`.
- **`_config.py`** — Frozen `EEPROMConfig` dataclass. No path fields; tools are bundled or found on PATH. `i2c_address` is `int` (e.g. `0x50`).
- **`_gpio.py`** — `WriteProtect` protocol, `GPIOWriteProtect` (real), `MockWriteProtect` (dev/test), `create_write_protect()` factory.
- **`_serial.py`** — `generate_serial_number()` standalone function.
- **`_tools.py`** — `_ToolPaths` (resolves bundled or system binaries via `importlib.resources`), `_run()` subprocess wrapper, `detect_i2c()`, `_eepflash_cmd()` builder, `_resolve_settings_template()`.
- **`_parser.py`** — `parse_eeprom_dump()` parses eepdump text output. Tries JSON then YAML for custom data.
- **`_eeprom.py`** — Main `EEPROM` class (6 public methods: `detect`, `read`, `read_device_tree`, `write`, `update`, `reset`) and `EEPROMContent` frozen dataclass. Uses `tempfile.TemporaryDirectory` for work files. Context manager support.
- **`__init__.py`** — Public API exports + `__version__`.

### CLI

- **`cli/_main.py`** — argparse CLI with subcommands `read`, `write`, `reset`. Entry point: `rpi-eeprom` (via pyproject.toml console_scripts).

### Vendor

- **`_vendor/bin/`** — Pre-compiled ARM64 binaries (eepmake, eepdump) and eepflash.sh. Populated by CI or manually.
- **`_vendor/templates/`** — Default `eeprom_settings.txt` HAT template.

### Tests

- **`tests/`** — Per-module test files with shared fixtures in `conftest.py`.

### Key design decisions

- **Tool resolution:** `_ToolPaths` tries bundled binaries first, then system PATH, then `/usr/local/bin`.
- **Error handling:** All failures raise typed exceptions (no bool returns).
- **GPIO:** Optional `gpiozero` dependency. Auto-detects platform and falls back to mock.
- **Temp files:** All intermediate files go into a `TemporaryDirectory`, cleaned up via context manager.
- **Multi-section custom data:** Supports multiple custom_data sections per EEPROM.

### Dependencies

- `pyyaml>=6.0` — YAML support (required)
- `gpiozero>=2.0` — GPIO control (optional, `pip install rpi-eeprom[gpio]`)
- `pytest`, `pytest-cov`, `ruff`, `mypy` — dev tools (`pip install rpi-eeprom[dev]`)

## EEPROM content requirements

A valid EEPROM must have non-zero `product_uuid` and a non-empty `serial_number` in its custom data. The CLI's `_handle_existing_content()` enforces this — blank or zero-UUID EEPROMs trigger re-initialization.
