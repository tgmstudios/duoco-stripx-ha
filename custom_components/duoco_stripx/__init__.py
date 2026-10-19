"""DuoCo StripX (MELK-OA21) local Bluetooth integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_ADDRESS, CONF_FIRMWARE, CONF_NAME
from .device import DuoCoStripXDevice

PLATFORMS = [Platform.LIGHT, Platform.NUMBER]

type DuoCoConfigEntry = ConfigEntry[DuoCoStripXDevice]


async def async_setup_entry(hass: HomeAssistant, entry: DuoCoConfigEntry) -> bool:
    # No device I/O here: setup never connects or writes.
    device = DuoCoStripXDevice(
        hass, entry.data[CONF_ADDRESS], entry.data.get(CONF_NAME, entry.title), entry.data.get(CONF_FIRMWARE)
    )
    device.async_start()
    entry.runtime_data = device
    entry.async_on_unload(entry.add_update_listener(_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _reload(hass: HomeAssistant, entry: DuoCoConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: DuoCoConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        await entry.runtime_data.async_stop()
    return ok
