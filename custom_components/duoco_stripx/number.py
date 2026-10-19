from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import DuoCoConfigEntry
from .entity import DuoCoEntity


async def async_setup_entry(hass: HomeAssistant, entry: DuoCoConfigEntry, add: AddEntitiesCallback) -> None:
    add([DuoCoSpeed(entry.runtime_data)])


class DuoCoSpeed(DuoCoEntity, RestoreEntity, NumberEntity):
    _attr_translation_key = "effect_speed"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER

    def __init__(self, device) -> None:
        super().__init__(device)
        self._attr_unique_id = f"{device.address}_speed"

    @property
    def native_value(self) -> float | None:
        return self._device.speed

    @property
    def extra_state_attributes(self) -> dict[str, float] | None:
        k = self._device.last_known
        if self._device.speed is None and k and k.get("speed") is not None:
            return {"last_known_value": k["speed"]}
        return None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            try:
                v = float(last.state)
            except (TypeError, ValueError):
                return
            if 0 <= v <= 100 and v == int(v):
                self._device.async_restore(speed=int(v))

    async def async_set_native_value(self, value: float) -> None:
        await self._device.async_command(speed=int(value))
