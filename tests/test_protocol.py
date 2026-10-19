"""Golden-vector and validation tests for the 9-byte frame builders."""
import math

import pytest

from custom_components.duoco_stripx.protocol import (
    ProtocolError,
    frame_brightness,
    frame_mode,
    frame_pixel_count,
    frame_power,
    frame_rgb,
    frame_speed,
)


def test_power_golden():
    assert frame_power(True).hex() == "7e0404010001ff00ef"
    assert frame_power(False).hex() == "7e0404000000ff00ef"


def test_rgb_golden():
    assert frame_rgb(255, 0, 0).hex() == "7e07050 3ff000010ef".replace(" ", "")
    assert frame_rgb(1, 2, 3).hex() == "7e070503010203" "10ef"


def test_brightness_speed_golden():
    assert frame_brightness(50).hex() == "7e040132ffffff00ef"
    assert frame_brightness(0).hex() == "7e040100ffffff00ef"
    assert frame_brightness(100).hex() == "7e040164ffffff00ef"
    assert frame_speed(50).hex() == "7e040232ffffff00ef"
    assert frame_speed(100).hex() == "7e040264ffffff00ef"


def test_mode_golden():
    assert frame_mode(3).hex() == "7e05030306ffff00ef"
    assert frame_mode(199).hex() == "7e050 3c706ffff00ef".replace(" ", "")  # 199 = 0xc7


def test_pixel_count_golden_little_endian():
    assert frame_pixel_count(10).hex() == "7e07210a000" "0ff00ef"
    assert frame_pixel_count(1000).hex() == "7e0721e803" "00ff00ef"


def test_all_frames_are_nine_bytes():
    for f in (frame_power(True), frame_rgb(0, 0, 0), frame_brightness(1), frame_speed(1), frame_mode(0), frame_pixel_count(300)):
        assert len(f) == 9 and f[0] == 0x7E and f[-1] == 0xEF


@pytest.mark.parametrize("bad", [-1, 101, True, False, 1.5, math.nan, math.inf, "5", None])
def test_brightness_and_speed_reject_invalid(bad):
    with pytest.raises(ProtocolError):
        frame_brightness(bad)
    with pytest.raises(ProtocolError):
        frame_speed(bad)


@pytest.mark.parametrize("bad", [-1, 256, True, 1.0, math.nan, "1", None])
def test_rgb_rejects_invalid(bad):
    for args in ((bad, 0, 0), (0, bad, 0), (0, 0, bad)):
        with pytest.raises(ProtocolError):
            frame_rgb(*args)


@pytest.mark.parametrize("bad", [-1, 256, True, 2.0, math.nan, None])
def test_mode_rejects_invalid(bad):
    with pytest.raises(ProtocolError):
        frame_mode(bad)


@pytest.mark.parametrize("bad", [9, 1001, True, 10.0, math.nan, None])
def test_pixel_count_rejects_invalid(bad):
    with pytest.raises(ProtocolError):
        frame_pixel_count(bad)


@pytest.mark.parametrize("bad", [1, 0, None, "on"])
def test_power_requires_real_bool(bad):
    with pytest.raises(ProtocolError):
        frame_power(bad)
