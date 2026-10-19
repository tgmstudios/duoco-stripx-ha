"""Pure 9-byte frame builders for the MELK-OA21 (fff3) protocol.

Frames are validated strictly: no clamping, no coercion. ``bool`` is never
accepted where an integer is required, and NaN/inf/floats are rejected.
Derived from the vendor app's observable command layout; Wi-Fi, CCT/white,
built-in scenes, LED geometry and pairing/init commands are intentionally absent.
"""

from __future__ import annotations

FRAME_LEN = 9


class ProtocolError(ValueError):
    """Raised for out-of-range or wrongly typed command values."""


def _int(value: object, lo: int, hi: int, what: str) -> int:
    if type(value) is not int:  # excludes bool, float, str, None
        raise ProtocolError(f"{what} must be an integer, got {value!r}")
    if not lo <= value <= hi:
        raise ProtocolError(f"{what} must be {lo}..{hi}, got {value}")
    return value


def frame_power(on: object) -> bytes:
    if type(on) is not bool:
        raise ProtocolError(f"power must be a bool, got {on!r}")
    v = 1 if on else 0
    return bytes([0x7E, 0x04, 0x04, v, 0x00, v, 0xFF, 0x00, 0xEF])


def frame_rgb(r: object, g: object, b: object) -> bytes:
    return bytes([0x7E, 0x07, 0x05, 0x03, _int(r, 0, 255, "red"), _int(g, 0, 255, "green"), _int(b, 0, 255, "blue"), 0x10, 0xEF])


def frame_brightness(percent: object) -> bytes:
    return bytes([0x7E, 0x04, 0x01, _int(percent, 0, 100, "brightness"), 0xFF, 0xFF, 0xFF, 0x00, 0xEF])


def frame_speed(percent: object) -> bytes:
    return bytes([0x7E, 0x04, 0x02, _int(percent, 0, 100, "speed"), 0xFF, 0xFF, 0xFF, 0x00, 0xEF])


def frame_mode(mode_id: object) -> bytes:
    return bytes([0x7E, 0x05, 0x03, _int(mode_id, 0, 255, "effect id"), 0x06, 0xFF, 0xFF, 0x00, 0xEF])


def frame_pixel_count(count: object) -> bytes:
    """App pixel-count frame. Persistent device config; not used automatically."""
    n = _int(count, 10, 1000, "pixel count")
    return bytes([0x7E, 0x07, 0x21, n & 0xFF, n >> 8, 0x00, 0xFF, 0x00, 0xEF])
