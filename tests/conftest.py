from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest_plugins = ["pytest_homeassistant_custom_component"]

ADDR = "AA:BB:CC:00:00:01"
ADDR2 = "AA:BB:CC:00:00:02"


@pytest.fixture(autouse=True)
def _auto_enable(enable_custom_integrations, hass):
    hass.config.components.add("bluetooth")  # avoid starting the real BT stack
    yield


class FakeClient:
    instances: list["FakeClient"] = []

    def __init__(self, fail_write_at: int | None = None, firmware: bytes = b"FW-TEST"):
        self.writes: list[tuple[str, bytes, bool]] = []
        self.connected = True
        self.disconnected = 0
        self.fail_write_at = fail_write_at
        self.firmware = firmware
        self.reads: list[str] = []
        FakeClient.instances.append(self)

    async def write_gatt_char(self, char, data, response=True):
        if self.fail_write_at is not None and len(self.writes) == self.fail_write_at:
            raise OSError("write failed")
        self.writes.append((char, bytes(data), response))

    async def read_gatt_char(self, char):
        self.reads.append(char)
        return bytearray(self.firmware)

    async def disconnect(self):
        self.disconnected += 1
        self.connected = False


@pytest.fixture
def ble(hass):
    """Patch BLE access; returns a controller for tests."""
    FakeClient.instances.clear()

    class Ctl:
        present = True
        connect_error: Exception | None = None
        next_client_kwargs: dict = {}
        establish = None

    ctl = Ctl()

    async def fake_establish(client_class, device, name, *a, **kw):
        if ctl.connect_error:
            raise ctl.connect_error
        return FakeClient(**ctl.next_client_kwargs)

    ctl.establish = AsyncMock(side_effect=fake_establish)
    ble_device = MagicMock()
    ble_device.address = ADDR
    ble_device.name = "MELK-OA21 test"
    avail_cbs = {}

    def reg(hass_, cb, matcher, mode):
        avail_cbs["seen"] = cb
        return lambda: avail_cbs.pop("seen", None)

    def track(hass_, cb, address, connectable=True):
        avail_cbs["gone"] = cb
        return lambda: avail_cbs.pop("gone", None)

    ctl.cbs = avail_cbs
    hass.config.components.add("bluetooth")
    with (
        patch("custom_components.duoco_stripx.device.establish_connection", ctl.establish),
        patch(
            "custom_components.duoco_stripx.device.bluetooth.async_ble_device_from_address",
            side_effect=lambda h, a, connectable=True: ble_device if ctl.present else None,
        ),
        patch(
            "custom_components.duoco_stripx.device.bluetooth.async_address_present",
            side_effect=lambda h, a, connectable=True: ctl.present,
        ),
        patch("custom_components.duoco_stripx.device.bluetooth.async_register_callback", side_effect=reg),
        patch("custom_components.duoco_stripx.device.bluetooth.async_track_unavailable", side_effect=track),
        patch("custom_components.duoco_stripx.device.WRITE_GAP", 0),
    ):
        yield ctl
