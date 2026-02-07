"""Parser for EEPROM text dump files produced by eepdump."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def parse_eeprom_dump(filepath: Path) -> dict[str, Any]:
    """Parse a human-readable EEPROM text dump into structured data.

    The dump file is produced by the ``eepdump`` tool and contains fields like
    product_uuid, product_id, vendor, product, and one or more custom_data
    sections.

    Custom data sections are tried as JSON first, then YAML, falling back to
    raw string storage.

    Returns:
        Dict with parsed EEPROM fields. Custom data is stored under
        ``custom_data_all`` as a list of all sections.
    """
    info: dict[str, Any] = {}
    custom_data_sections: list[Any] = []

    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            if line.startswith("product_uuid"):
                info["product_uuid"] = line.split()[1]
            elif line.startswith("product_id"):
                info["product_id"] = line.split()[1]
            elif line.startswith("product_ver"):
                info["product_ver"] = line.split()[1]
            elif line.startswith("vendor"):
                info["vendor"] = line.split('"')[1]
            elif line.startswith("product"):
                info["product"] = line.split('"')[1]
            elif line.startswith("dt_blob"):
                info["dt_blob"] = line.split('"')[1]
            elif line.startswith("custom_data"):
                logger.debug("Found custom_data section")
                custom_data_lines: list[str] = []
                while True:
                    data_line = f.readline().strip()
                    if not data_line:
                        continue
                    if data_line.endswith('\\"'):
                        custom_data_lines.append(data_line[:-2])
                        break
                    custom_data_lines.append(data_line)

                if custom_data_lines:
                    raw = "".join(custom_data_lines).strip().strip('"')
                    logger.debug("Raw custom data: %s", raw)
                    parsed = _try_parse_custom_data(raw)
                    custom_data_sections.append(parsed)

    if custom_data_sections:
        info["custom_data_all"] = custom_data_sections

    return info


def _try_parse_custom_data(raw: str) -> Any:
    """Try to parse a custom data string as JSON, then YAML, then raw string."""
    try:
        parsed = json.loads(raw)
        logger.info("Successfully parsed custom data as JSON")
        return parsed
    except json.JSONDecodeError:
        logger.debug("JSON parsing failed, trying YAML")

    try:
        parsed = yaml.safe_load(raw)
        logger.info("Successfully parsed custom data as YAML")
        return parsed
    except yaml.YAMLError:
        logger.debug("YAML parsing failed")

    logger.warning("Failed to parse as JSON or YAML, storing as string")
    return raw
