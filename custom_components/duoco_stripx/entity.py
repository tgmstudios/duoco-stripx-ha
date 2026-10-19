from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .device import DuoCoStripXDevice


class DuoCoEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_assumed_state = True  # the controller never reports its state

    def __init__(self, device: DuoCoStripXDevice) -> None:
        self._device = device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.address)},
            connections={(CONNECTION_BLUETOOTH, device.address)},
            name=device.name,
            manufacturer="DuoCo",
            model="StripX (MELK-OA21)",
            sw_version=device.firmware or None,
        )

    @property
    def available(self) -> bool:
        return self._device.available

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._device.async_add_listener(self.async_write_ha_state))
