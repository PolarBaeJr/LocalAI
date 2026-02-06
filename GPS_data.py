"""
GPS/Location helper utilities.

This module provides lightweight helpers to:
- detect when a user request likely requires location/GPS data
- generate a user-facing prompt asking them to provide location information

Note: The app cannot access device GPS directly; location must be supplied
by the user or via an external trusted service.
"""

from __future__ import annotations

import re
from typing import Tuple

from logic import LOCATION_KEYWORDS


def needs_location(prompt: str) -> bool:
    """Heuristic to decide if the prompt likely needs location data."""
    text = prompt.lower()
    if any(k in text for k in LOCATION_KEYWORDS):
        return True
    # Look for explicit lat/long patterns
    if re.search(r"\b[-+]?[0-9]{1,3}\.[0-9]{3,}\b", text):
        return True
    return False


def location_request_message() -> str:
    """Standard message requesting location details from the user."""
    return (
        "I don't have access to your device's GPS. "
        "Please share your location (city/country) or approximate coordinates "
        "(lat, long) so I can tailor the answer."
    )


def handle_location_requirement(prompt: str) -> Tuple[bool, str | None]:
    """
    Convenience wrapper: returns (location_needed, message_or_none).
    If location is likely needed, message contains the standard request.
    """
    need_loc = needs_location(prompt)
    return need_loc, location_request_message() if need_loc else None
