"""Serial number generation for EEPROM devices."""

from __future__ import annotations

import random

_CHARSET = "ABCDEFGHJKLMNPQRSTUVWXYZ0123456789"


def generate_serial_number(length: int = 12) -> str:
    """Generate a random serial number.

    Uses SystemRandom for cryptographically secure randomness.
    Character set excludes ambiguous characters (I, O) for readability.
    """
    return "".join(random.SystemRandom().choice(_CHARSET) for _ in range(length))
