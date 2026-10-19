"""Per-device BLE access: on-demand connect, serialized bounded writes, assumed state."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError

from .const import CHAR_UUID, CONNECT_ATTEMPTS, DISCONNECT_TIMEOUT, OPERATION_TIMEOUT
from .protocol import (
    ProtocolError,
    frame_brightness,
    frame_mode,
    frame_power,
    frame_rgb,
    frame_speed,
)

_LOGGER = logging.getLogger(__name__)
WRITE_GAP = 0.05  # seconds between frames (the vendor app paces writes similarly)

_BLE_ERRORS = (BleakError, OSError, TimeoutError, asyncio.TimeoutError)


_DISCONNECT_TASKS: set[asyncio.Future] = set()


def _reap_disconnect(task: asyncio.Future) -> None:
    _DISCONNECT_TASKS.discard(task)
    if not task.cancelled():
        task.exception()  # retrieve so a late failure never logs "never retrieved"


async def _cancel_and_reap(task: asyncio.Future) -> None:
    """Cancel a disconnect task and give it a bounded chance to finish unwinding."""
    task.cancel()
    try:
        await asyncio.wait({task}, timeout=DISCONNECT_TIMEOUT)
    except asyncio.CancelledError:  # repeated cancel: task already cancelled and tracked
        pass


async def _safe_disconnect(client) -> None:
    """Disconnect with a hard bound. Never raises ordinary errors; never waits past the timeout.

    The disconnect runs as a tracked task: on timeout or on cancellation of the caller it is
    cancelled (not left running in the background) and its result is always retrieved.
    """
    task = asyncio.ensure_future(client.disconnect())
    _DISCONNECT_TASKS.add(task)
    task.add_done_callback(_reap_disconnect)
    try:
        done, _ = await asyncio.wait({task}, timeout=DISCONNECT_TIMEOUT)
    except BaseException:
        await _cancel_and_reap(task)  # caller cancelled (possibly repeatedly): don't orphan it
        raise
    if not done:
        _LOGGER.warning("Bluetooth disconnect timed out after %ss; abandoning", DISCONNECT_TIMEOUT)
        await _cancel_and_reap(task)


async def async_read_firmware(hass: HomeAssistant, address: str) -> str:
    """Connect, read the fff3 characteristic (firmware string), disconnect. No writes."""
    ble_device = bluetooth.async_ble_device_from_address(hass, address, connectable=True)
    if ble_device is None:
        raise HomeAssistantError("Device not currently visible to any Bluetooth adapter")
    client = None
    try:
        async with asyncio.timeout(OPERATION_TIMEOUT):
            client = await establish_connection(
                BleakClientWithServiceCache, ble_device, address, max_attempts=CONNECT_ATTEMPTS
            )
            raw = await client.read_gatt_char(CHAR_UUID)
    except _BLE_ERRORS as err:
        raise HomeAssistantError(f"Could not read device: {err}") from err
    finally:
        if client is not None:
            await _safe_disconnect(client)
    return bytes(raw).decode("ascii", errors="ignore").strip("\x00 \r\n")


class DuoCoStripXDevice:
    """One physical controller. State is OPTIMISTIC: the device reports nothing back."""

    def __init__(self, hass: HomeAssistant, address: str, name: str, firmware: str | None = None) -> None:
        self.hass = hass
        self.address = address
        self.name = name
        self.firmware = firmware
        self._lock = asyncio.Lock()
        self._listeners: list[Callable[[], None]] = []
        self._unsubs: list[Callable[[], None]] = []
        self._stopped = False
        self._seen = False
        self._failed = False
        self.is_on: bool | None = None
        self.rgb: tuple[int, int, int] | None = None
        self.brightness: int | None = None  # percent 0..100
        self.effect_id: int | None = None
        self.speed: int | None = None  # percent 0..100
        # Values restored after a restart. Diagnostic only: NOT presented as current state.
        self.last_known: dict | None = None

    # -- lifecycle -------------------------------------------------------
    @callback
    def async_start(self) -> None:
        self._seen = bluetooth.async_address_present(self.hass, self.address, connectable=True)
        self._unsubs.append(
            bluetooth.async_register_callback(
                self.hass,
                self._on_advert,
                {"address": self.address, "connectable": True},
                bluetooth.BluetoothScanningMode.PASSIVE,
            )
        )
        self._unsubs.append(
            bluetooth.async_track_unavailable(self.hass, self._on_gone, self.address, connectable=True)
        )

    async def async_stop(self) -> None:
        self._stopped = True
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        async with self._lock:  # let an in-flight command finish its cleanup
            pass
        self._notify()

    # -- availability (passive, no connections) -----------------------------
    @property
    def available(self) -> bool:
        return not self._stopped and self._seen and not self._failed

    @callback
    def _on_advert(self, service_info, change) -> None:
        self._seen = True
        self._failed = False
        self._notify()

    @callback
    def _on_gone(self, service_info) -> None:
        self._seen = False
        self._clear_state()  # power cycle likely: cached command state may be false
        self._notify()

    # -- listeners ---------------------------------------------------------
    def async_add_listener(self, cb: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(cb)

        def remove() -> None:
            if cb in self._listeners:
                self._listeners.remove(cb)

        return remove

    @callback
    def _notify(self) -> None:
        for cb in list(self._listeners):
            cb()

    # -- restore (diagnostic only, never written, never presented as current state) --
    @callback
    def async_restore(self, *, on=None, rgb=None, brightness=None, effect_id=None, speed=None) -> None:
        """Remember last-known values for diagnostics. State stays unknown until a command is sent."""
        known = dict(self.last_known or {})
        if on is not None:
            known.update(on=on, rgb=rgb, brightness=brightness, effect_id=effect_id)
        if speed is not None:
            known["speed"] = speed
        self.last_known = known or None
        self._notify()

    # -- commands ----------------------------------------------------------
    async def async_command(
        self,
        *,
        on: bool | None = None,
        rgb: tuple[int, int, int] | None = None,
        brightness: int | None = None,
        effect_id: int | None = None,
        speed: int | None = None,
    ) -> None:
        try:
            frames: list[bytes] = []
            if on is not None:
                frames.append(frame_power(on))
            if rgb is not None:
                frames.append(frame_rgb(*rgb))
            if effect_id is not None:
                frames.append(frame_mode(effect_id))
            if brightness is not None:
                frames.append(frame_brightness(brightness))
            if speed is not None:
                frames.append(frame_speed(speed))
        except (ProtocolError, TypeError) as err:
            raise HomeAssistantError(str(err)) from err
        if not frames:
            return
        if self._stopped:
            raise HomeAssistantError("Integration is unloaded")

        try:
            async with self._lock:
                if self._stopped:
                    raise HomeAssistantError("Integration is unloaded")

                def apply() -> None:
                    # Called right after the last frame was written (before disconnect), so a
                    # cancel during cleanup cannot leave the old state in place. ACK != light state.
                    if on is not None:
                        self.is_on = on
                    if rgb is not None:
                        self.rgb = tuple(rgb)
                        self.effect_id = None
                    if effect_id is not None:
                        self.effect_id = effect_id
                    if brightness is not None:
                        self.brightness = brightness
                    if speed is not None:
                        self.speed = speed
                    self._failed = False

                await self._send(frames, apply)
        finally:
            self._notify()

    async def _send(self, frames: list[bytes], apply: Callable[[], None]) -> None:
        ble_device = bluetooth.async_ble_device_from_address(self.hass, self.address, connectable=True)
        if ble_device is None:
            raise HomeAssistantError("Device is not in Bluetooth range")
        client = None
        attempted = False  # a write may have reached the device
        applied = False
        try:
            async with asyncio.timeout(OPERATION_TIMEOUT):
                client = await establish_connection(
                    BleakClientWithServiceCache,
                    ble_device,
                    self.name,
                    max_attempts=CONNECT_ATTEMPTS,
                    ble_device_callback=lambda: bluetooth.async_ble_device_from_address(
                        self.hass, self.address, connectable=True
                    )
                    or ble_device,
                )
                for i, frame in enumerate(frames):
                    if i:
                        await asyncio.sleep(WRITE_GAP)
                    attempted = True  # set before the call: a cancel/raise inside it is uncertain
                    await client.write_gatt_char(CHAR_UUID, frame, response=False)
                apply()
                applied = True
        except _BLE_ERRORS as err:
            self._mark_failed()
            raise HomeAssistantError(f"Bluetooth command failed: {err}") from err
        except BaseException:
            # CancelledError etc.: never convert, but state is stale if a write may have happened
            # and the command did not complete. Cancel before any write leaves state untouched.
            if attempted and not applied:
                self._mark_failed()
            raise
        finally:
            if client is not None:
                await _safe_disconnect(client)

    def _mark_failed(self) -> None:
        """Physical state is now uncertain: forget assumed values, flag unavailable."""
        self._failed = True
        self._clear_state()
        self._notify()

    def _clear_state(self) -> None:
        self.is_on = None
        self.rgb = None
        self.brightness = None
        self.effect_id = None
        self.speed = None
