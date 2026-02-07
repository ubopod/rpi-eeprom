# rpi-eeprom

Raspberry Pi EEPROM management tool for reading, writing, and managing EEPROM content on RPi HAT devices. Supports JSON and YAML custom data formats with multi-section storage.

## Installation

```bash
pip install rpi-eeprom
```

On a Raspberry Pi with GPIO hardware access:

```bash
pip install rpi-eeprom[gpio]
```

### Prerequisites

EEPROM hardware operations require `eepmake`, `eepdump`, and `eepflash.sh` from the [Raspberry Pi utils](https://github.com/raspberrypi/utils) eeptools. Pre-compiled ARM64 binaries are bundled in release builds. If using a source install, compile them manually:

```bash
git clone https://github.com/raspberrypi/utils
cd utils/eeptools
cmake .
make
sudo make install
```

The I2C bus overlay must be loaded before use:

```bash
sudo dtoverlay i2c-gpio i2c_gpio_sda=0 i2c_gpio_scl=1 bus=9
```

> **Note:** Most EEPROM operations require `sudo` for hardware access.

## Python Library

```python
from rpi_eeprom import EEPROM, EEPROMConfig

# Use default configuration (bus=9, address=0x50, model=24c32)
with EEPROM() as eeprom:
    # Read EEPROM content
    content = eeprom.read()
    print(content.product_uuid)
    print(content.vendor)
    print(content.serial_number)  # From first custom data section
    print(content.custom_data)    # All custom data sections

    # Write new content (resets EEPROM first)
    eeprom.write(custom_data=[{"serial_number": "ABC123XYZ"}])

    # Update custom data while preserving UUID and settings
    eeprom.update(custom_data=[{"serial_number": "NEW456"}])

    # Append a new custom data section
    eeprom.update(custom_data=[{"extra": "data"}], append=True)

    # Replace a specific section by index
    eeprom.update(custom_data=[{"replaced": True}], index=1)

    # Reset to blank
    eeprom.reset()
```

### Custom configuration

```python
config = EEPROMConfig(
    model="24c64",
    size_kbytes=8,
    i2c_bus=1,
    i2c_address=0x51,
    write_protect_pin=17,
    settings_template="/path/to/custom_settings.txt",
)

with EEPROM(config) as eeprom:
    content = eeprom.read()
```

### Reading from device tree

```python
with EEPROM() as eeprom:
    # Read how Linux currently sees the EEPROM via /proc/device-tree/
    # (reflects state at boot, not live changes)
    data = eeprom.read_device_tree(index=0)
    print(data["serial_number"])
```

### Writing custom data from files

```python
from pathlib import Path

with EEPROM() as eeprom:
    # Write from JSON/YAML files
    eeprom.write(custom_data=[
        Path("config.json"),
        Path("metadata.yaml"),
    ])

    # Mix files and dicts
    eeprom.write(custom_data=[
        Path("config.json"),
        {"serial_number": "ABC123"},
    ])
```

### Error handling

All operations raise typed exceptions instead of returning booleans:

```python
from rpi_eeprom import (
    EEPROM,
    EEPROMNotFoundError,
    EEPROMReadError,
    EEPROMWriteError,
    EEPROMConfigError,
)

try:
    with EEPROM() as eeprom:
        content = eeprom.read()
except EEPROMNotFoundError:
    print("No EEPROM device detected on I2C bus")
except EEPROMReadError:
    print("Failed to read EEPROM content")
except EEPROMWriteError:
    print("Failed to write to EEPROM")
except EEPROMConfigError:
    print("Invalid configuration")
```

## CLI

The `rpi-eeprom` command provides three subcommands: `read`, `write`, and `reset`.

### Read EEPROM content

```bash
# Read and display as JSON (default)
rpi-eeprom read

# Read as YAML
rpi-eeprom read --format yaml

# Save to a file (format auto-detected from extension)
rpi-eeprom read --output eeprom_data.yaml

# Read a specific custom data section
rpi-eeprom read --index 1

# Read from device tree instead of hardware
rpi-eeprom read --device-tree
rpi-eeprom read --device-tree --index 1
```

### Write to EEPROM

```bash
# Write custom data from a JSON file
rpi-eeprom write --data config.json

# Write multiple custom data sections
rpi-eeprom write --data section1.json --data section2.yaml

# Append new sections while preserving existing ones
rpi-eeprom write --data new_section.json --append

# Replace a specific section by index
rpi-eeprom write --data replacement.json --index 1

# Update the serial number
rpi-eeprom write --serial ABC123XYZ

# Auto-detect and handle existing content
rpi-eeprom write
rpi-eeprom write --force  # Force overwrite corrupt content
```

### Reset EEPROM

```bash
# Reset EEPROM to blank state (all zeros)
rpi-eeprom reset
```

### Configuration file

Use `--config` to specify EEPROM hardware settings (JSON or YAML):

```bash
rpi-eeprom --config my_config.yaml read
```

Example `config.yaml`:

```yaml
model: 24c64
size_kbytes: 8
i2c_bus: 1
i2c_address: 0x51
write_protect_pin: 17
```

### Verbose output

```bash
rpi-eeprom -v read
```

## EEPROM Content

A valid EEPROM contains a product UUID, vendor/product info, and one or more custom data sections. Each custom data section can be JSON or YAML.

```
product_uuid 12345678-1234-5678-1234-567812345678
product_id 0x0105
product_ver 0x0001
vendor "Ubo Technology Company"
product "Ubo HAT+"
custom_data "
{"serial_number": "ZF64JA81VPPZ", "eeprom": {"model": "24c32"}}
\"
```

A valid EEPROM must have a non-zero `product_uuid` and a `serial_number` in its first custom data section. Blank or zero-UUID EEPROMs are automatically re-initialized when using the CLI `write` command.

## Development

```bash
# Install in development mode with all dev tools
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=rpi_eeprom

# Lint
ruff check src/ tests/

# Type check
mypy src/rpi_eeprom/
```

## License

Apache License 2.0 - see [LICENSE](LICENSE) for details.

Pre-compiled eeptools binaries (eepmake, eepdump, eepflash.sh) are from [raspberrypi/utils](https://github.com/raspberrypi/utils) under the BSD 3-Clause License - see [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES).
