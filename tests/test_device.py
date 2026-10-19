import asyncio

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.duoco_stripx.const import CHAR_UUID
from custom_components.duoco_stripx.device import DuoCoStripXDevice, async_read_firmware
from .conftest import ADDR, ADDR2, FakeClient


async def test_command_connects_writes_without_response_and_disconnects(hass, ble):
    dev = DuoCoStripXDevice(hass, ADDR, "n")
    dev.async_start()
    await dev.async_command(on=True, rgb=(255, 0, 0), brightness=50)
    (c,) = FakeClient.instances
    assert [w[1].hex() for w in c.writes] == [
        "7e0404010001ff00ef",
        "7e070503ff000010ef",
        "7e040132ffffff00ef",
    ]
    assert all(w[0] == CHAR_UUID and w[2] is False for w in c.writes)
    assert c.disconnected == 1
    assert (dev.is_on, dev.rgb, dev.brightness, dev.effect_id) == (True, (255, 0, 0), 50, None)


async def test_no_writes_or_connections_on_start(hass, ble):
    dev = DuoCoStripXDevice(hass, ADDR, "n")
    dev.async_start()
    assert ble.establish.call_count == 0
    assert dev.is_on is None and dev.rgb is None


async def test_effect_replaces_rgb_and_brightness_preserved(hass, ble):
    dev = DuoCoStripXDevice(hass, ADDR, "n")
    dev.async_start()
    await dev.async_command(rgb=(1, 2, 3), brightness=40)
    await dev.async_command(effect_id=3)
    assert dev.effect_id == 3 and dev.rgb == (1, 2, 3) and dev.brightness == 40
    assert FakeClient.instances[-1].writes[-1][1].hex() == "7e05030306ffff00ef"
    await dev.async_command(brightness=10)  # color/effect untouched
    assert dev.effect_id == 3 and dev.rgb == (1, 2, 3)
    await dev.async_command(rgb=(9, 9, 9))
    assert dev.effect_id is None


async def test_invalid_input_raises_before_any_connection(hass, ble):
    dev = DuoCoStripXDevice(hass, ADDR, "n")
    dev.async_start()
    for kw in ({"brightness": 101}, {"speed": True}, {"rgb": (256, 0, 0)}, {"effect_id": float("nan")}):
        with pytest.raises(HomeAssistantError):
            await dev.async_command(**kw)
    assert ble.establish.call_count == 0


async def test_write_failure_is_atomic_disconnects_and_marks_unavailable(hass, ble):
    dev = DuoCoStripXDevice(hass, ADDR, "n")
    dev.async_start()
    await dev.async_command(on=True, rgb=(1, 1, 1))
    ble.next_client_kwargs = {"fail_write_at": 1}
    with pytest.raises(HomeAssistantError):
        await dev.async_command(on=True, rgb=(5, 5, 5))
    assert FakeClient.instances[-1].disconnected == 1
    assert dev.available is False
    # state reset to unknown, not pretend-applied
    assert dev.rgb != (5, 5, 5) and dev.is_on is None


async def test_connect_failure_raises_and_marks_unavailable(hass, ble):
    dev = DuoCoStripXDevice(hass, ADDR, "n")
    dev.async_start()
    ble.connect_error = TimeoutError()
    with pytest.raises(HomeAssistantError):
        await dev.async_command(on=True)
    assert dev.available is False


async def test_device_not_in_range_raises(hass, ble):
    dev = DuoCoStripXDevice(hass, ADDR, "n")
    dev.async_start()
    ble.present = False
    with pytest.raises(HomeAssistantError):
        await dev.async_command(on=True)
    assert ble.establish.call_count == 0


async def test_availability_from_passive_callbacks(hass, ble):
    dev = DuoCoStripXDevice(hass, ADDR, "n")
    ble.present = False
    dev.async_start()
    assert dev.available is False
    ble.cbs["seen"](object(), object())
    assert dev.available is True
    ble.cbs["gone"](object())
    assert dev.available is False


async def test_listeners_notified(hass, ble):
    dev = DuoCoStripXDevice(hass, ADDR, "n")
    dev.async_start()
    calls = []
    unsub = dev.async_add_listener(lambda: calls.append(1))
    await dev.async_command(on=False)
    assert calls
    unsub()
    n = len(calls)
    await dev.async_command(on=True)
    assert len(calls) == n


async def test_commands_are_serialised(hass, ble):
    dev = DuoCoStripXDevice(hass, ADDR, "n")
    dev.async_start()
    active = 0
    peak = 0
    orig = ble.establish.side_effect

    async def slow(*a, **k):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        c = await orig(*a, **k)
        orig_dis = c.disconnect

        async def dis():
            nonlocal active
            active -= 1
            await orig_dis()

        c.disconnect = dis
        return c

    ble.establish.side_effect = slow
    await asyncio.gather(*(dev.async_command(brightness=i) for i in range(1, 5)))
    assert peak == 1 and len(FakeClient.instances) == 4


async def test_multi_device_independent_locks_and_state(hass, ble):
    a = DuoCoStripXDevice(hass, ADDR, "a")
    b = DuoCoStripXDevice(hass, ADDR2, "b")
    a.async_start()
    b.async_start()
    assert a._lock is not b._lock
    await a.async_command(rgb=(1, 0, 0))
    assert b.rgb is None


async def test_stop_blocks_further_commands_and_cleans_up(hass, ble):
    dev = DuoCoStripXDevice(hass, ADDR, "n")
    dev.async_start()
    await dev.async_stop()
    assert ble.cbs == {}
    with pytest.raises(HomeAssistantError):
        await dev.async_command(on=True)


async def test_cancel_mid_write_still_disconnects(hass, ble):
    dev = DuoCoStripXDevice(hass, ADDR, "n")
    dev.async_start()
    started = asyncio.Event()

    async def slow_write(self, char, data, response=True):
        started.set()
        await asyncio.sleep(10)

    FakeClient.write_gatt_char, orig = slow_write, FakeClient.write_gatt_char
    try:
        t = asyncio.create_task(dev.async_command(on=True))
        await started.wait()
        t.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t
    finally:
        FakeClient.write_gatt_char = orig
    assert FakeClient.instances[-1].disconnected == 1


async def test_read_firmware_is_read_only(hass, ble):
    fw = await async_read_firmware(hass, ADDR)
    c = FakeClient.instances[-1]
    assert fw == "FW-TEST" and c.writes == [] and c.reads == [CHAR_UUID] and c.disconnected == 1


async def test_read_firmware_errors(hass, ble):
    ble.present = False
    with pytest.raises(HomeAssistantError):
        await async_read_firmware(hass, ADDR)
    ble.present = True
    ble.connect_error = OSError()
    with pytest.raises(HomeAssistantError):
        await async_read_firmware(hass, ADDR)


# -- bounded disconnect / cancellation-state regressions ------------------------


def _hang_disconnect(monkeypatch, cancelled: list):
    async def hang(self):
        self.disconnected += 1
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            cancelled.append(1)
            raise

    monkeypatch.setattr(FakeClient, "disconnect", hang)


async def test_hung_disconnect_is_bounded_releases_lock_and_stop(hass, ble, monkeypatch):
    monkeypatch.setattr("custom_components.duoco_stripx.device.DISCONNECT_TIMEOUT", 0.01)
    cancelled: list = []
    _hang_disconnect(monkeypatch, cancelled)
    dev = DuoCoStripXDevice(hass, ADDR, "n")
    dev.async_start()
    await asyncio.wait_for(dev.async_command(on=True), 1)
    assert dev.is_on is True and cancelled  # hung disconnect task was cancelled, not orphaned
    await asyncio.wait_for(dev.async_command(brightness=5), 1)  # lock was released
    await asyncio.wait_for(dev.async_stop(), 1)


async def test_hung_disconnect_bounded_in_firmware_read(hass, ble, monkeypatch):
    monkeypatch.setattr("custom_components.duoco_stripx.device.DISCONNECT_TIMEOUT", 0.01)
    _hang_disconnect(monkeypatch, [])
    assert await asyncio.wait_for(async_read_firmware(hass, ADDR), 1) == "FW-TEST"


async def test_repeated_cancel_during_disconnect_cleanup_stays_bounded(hass, ble, monkeypatch):
    monkeypatch.setattr("custom_components.duoco_stripx.device.DISCONNECT_TIMEOUT", 0.2)
    cancelled: list = []
    _hang_disconnect(monkeypatch, cancelled)
    dev = DuoCoStripXDevice(hass, ADDR, "n")
    dev.async_start()
    t = asyncio.create_task(dev.async_command(on=True))
    while not FakeClient.instances or not FakeClient.instances[-1].disconnected:
        await asyncio.sleep(0)
    t.cancel()
    await asyncio.sleep(0)
    t.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(t, 1)
    assert cancelled
    # all frames were written before the cancel, so the state is applied, lock free
    assert dev.is_on is True
    await asyncio.wait_for(dev.async_command(on=False), 1.5)


async def _prime(hass, ble):
    dev = DuoCoStripXDevice(hass, ADDR, "n")
    dev.async_start()
    await dev.async_command(on=True, rgb=(1, 2, 3), brightness=50, speed=20)
    assert dev.is_on is True
    return dev


async def test_cancel_between_frames_clears_assumed_state(hass, ble, monkeypatch):
    dev = await _prime(hass, ble)
    gate = asyncio.Event()
    count = 0
    orig = FakeClient.write_gatt_char

    async def write(self, char, data, response=True):
        nonlocal count
        count += 1
        if count == 2:
            gate.set()
            await asyncio.sleep(3600)
        await orig(self, char, data, response)

    monkeypatch.setattr(FakeClient, "write_gatt_char", write)
    t = asyncio.create_task(dev.async_command(on=False, rgb=(9, 9, 9)))
    await gate.wait()
    t.cancel()
    with pytest.raises(asyncio.CancelledError):
        await t
    assert FakeClient.instances[-1].disconnected == 1
    assert (dev.is_on, dev.rgb, dev.brightness, dev.effect_id, dev.speed) == (None, None, None, None, None)
    assert dev.available is False


async def test_cancel_during_first_write_is_uncertain(hass, ble, monkeypatch):
    dev = await _prime(hass, ble)
    started = asyncio.Event()

    async def write(self, char, data, response=True):
        started.set()
        await asyncio.sleep(3600)

    monkeypatch.setattr(FakeClient, "write_gatt_char", write)
    t = asyncio.create_task(dev.async_command(on=False))
    await started.wait()
    t.cancel()
    with pytest.raises(asyncio.CancelledError):
        await t
    assert dev.is_on is None and dev.available is False


async def test_cancel_before_any_write_keeps_state(hass, ble):
    dev = await _prime(hass, ble)
    started = asyncio.Event()
    orig = ble.establish.side_effect

    async def slow(*a, **k):
        started.set()
        await asyncio.sleep(3600)

    ble.establish.side_effect = slow
    t = asyncio.create_task(dev.async_command(on=False))
    await started.wait()
    t.cancel()
    with pytest.raises(asyncio.CancelledError):
        await t
    ble.establish.side_effect = orig
    assert dev.is_on is True and dev.rgb == (1, 2, 3) and dev.available is True


async def test_cancel_mid_write_waiter_proceeds_and_stop_bounded(hass, ble, monkeypatch):
    monkeypatch.setattr("custom_components.duoco_stripx.device.DISCONNECT_TIMEOUT", 0.01)
    dev = await _prime(hass, ble)
    started = asyncio.Event()
    orig = FakeClient.write_gatt_char
    hang = True

    async def write(self, char, data, response=True):
        if hang:
            started.set()
            await asyncio.sleep(3600)
        await orig(self, char, data, response)

    monkeypatch.setattr(FakeClient, "write_gatt_char", write)
    first = asyncio.create_task(dev.async_command(on=False))
    await started.wait()
    waiter = asyncio.create_task(dev.async_command(brightness=70))
    await asyncio.sleep(0)
    first.cancel()
    hang = False
    with pytest.raises(asyncio.CancelledError):
        await first
    await asyncio.wait_for(waiter, 1)
    assert dev.brightness == 70
    await asyncio.wait_for(dev.async_stop(), 1)


async def test_keyboard_interrupt_is_not_suppressed(hass, ble, monkeypatch):
    dev = await _prime(hass, ble)

    async def write(self, char, data, response=True):
        raise KeyboardInterrupt

    monkeypatch.setattr(FakeClient, "write_gatt_char", write)
    with pytest.raises(KeyboardInterrupt):
        await dev.async_command(on=False)
    assert dev.is_on is None


async def test_advert_loss_clears_command_known_state(hass, ble):
    dev = await _prime(hass, ble)
    ble.cbs["gone"](object())
    assert (dev.is_on, dev.rgb, dev.brightness, dev.effect_id, dev.speed) == (None, None, None, None, None)
    ble.cbs["seen"](object(), object())
    assert dev.available is True and dev.is_on is None


async def test_restore_is_diagnostic_only(hass, ble):
    dev = DuoCoStripXDevice(hass, ADDR, "n")
    dev.async_start()
    dev.async_restore(on=True, rgb=(1, 2, 3), brightness=40, effect_id=None, speed=30)
    assert (dev.is_on, dev.rgb, dev.brightness, dev.speed) == (None, None, None, None)
    assert dev.last_known == {"on": True, "rgb": (1, 2, 3), "brightness": 40, "effect_id": None, "speed": 30}
    assert ble.establish.call_count == 0
