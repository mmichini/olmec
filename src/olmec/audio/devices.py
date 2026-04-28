"""Helpers for selecting audio input/output devices by name substring."""

import logging

logger = logging.getLogger(__name__)


def find_device_by_name(name_substring: str, kind: str) -> int | None:
    """Find a sounddevice device by substring match on its name.

    kind: "input" or "output"
    Returns the device index, or None if not found.
    """
    if not name_substring:
        return None
    try:
        import sounddevice as sd
        devices = sd.query_devices()
    except Exception:
        logger.exception("Failed to query audio devices")
        return None

    name_lower = name_substring.lower()
    needs_input = kind == "input"
    needs_output = kind == "output"

    for idx, dev in enumerate(devices):
        if needs_input and dev.get("max_input_channels", 0) <= 0:
            continue
        if needs_output and dev.get("max_output_channels", 0) <= 0:
            continue
        if name_lower in dev["name"].lower():
            logger.info(f"Selected {kind} device [{idx}]: {dev['name']}")
            return idx

    logger.warning(f"No {kind} device matched name substring: {name_substring!r}")
    return None


def list_devices() -> str:
    """Return a human-readable listing of all audio devices."""
    try:
        import sounddevice as sd
        return str(sd.query_devices())
    except Exception as e:
        return f"Failed to query devices: {e}"
