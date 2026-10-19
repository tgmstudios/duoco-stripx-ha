from __future__ import annotations

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_EFFECT,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.const import STATE_ON, STATE_OFF
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import DuoCoConfigEntry
from .const import OPT_ALLOW_FLASHING
from .effects import effect_by_id, effect_by_label, effects_for
from .entity import DuoCoEntity


def _to_pct(b: int) -> int:
    return max(1, round(b * 100 / 255)) if b > 0 else 0


def _from_pct(p: int) -> int:
    return int(p * 255 / 100 + 0.5)


async def async_setup_entry(hass: HomeAssistant, entry: DuoCoConfigEntry, add: AddEntitiesCallback) -> None:
    add([DuoCoLight(entry.runtime_data, bool(entry.options.get(OPT_ALLOW_FLASHING, False)))])


class DuoCoLight(DuoCoEntity, RestoreEntity, LightEntity):
    _attr_name = None
    _attr_color_mode = ColorMode.RGB
    _attr_supported_color_modes = {ColorMode.RGB}
    _attr_supported_features = LightEntityFeature.EFFECT

    def __init__(self, device, allow_flashing: bool) -> None:
        super().__init__(device)
        self._allow_flashing = allow_flashing
        self._attr_unique_id = f"{device.address}_light"
        self._attr_effect_list = [e.label for e in effects_for(allow_flashing)]

    @property
    def is_on(self) -> bool | None:
        return self._device.is_on

    @property
    def rgb_color(self):
        return self._device.rgb

    @property
    def brightness(self) -> int | None:
        p = self._device.brightness
        return None if p is None else _from_pct(p)

    @property
    def effect(self) -> str | None:
        eid = self._device.effect_id
        e = None if eid is None else effect_by_id(eid)
        return e.label if e else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Restored values are exposed only as last_known_*; they are not the current state."""
        k = self._device.last_known
        if not k or self._device.is_on is not None or "on" not in k:
            return None
        out: dict[str, Any] = {"last_known_state": STATE_ON if k["on"] else STATE_OFF}
        if k.get("rgb"):
            out["last_known_rgb_color"] = tuple(k["rgb"])
        if k.get("brightness") is not None:
            out["last_known_brightness"] = _from_pct(k["brightness"])
        return out

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is None or last.state not in (STATE_ON, STATE_OFF):
            return
        a = last.attributes
        rgb = a.get("rgb_color")
        eff = effect_by_label(a["effect"], self._allow_flashing) if a.get("effect") else None
        bri = a.get("brightness")
        self._device.async_restore(
            on=last.state == STATE_ON,
            rgb=tuple(rgb) if rgb else None,
            brightness=_to_pct(bri) if isinstance(bri, int) else None,
            effect_id=eff.id if eff else None,
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        effect_id = None
        if (label := kwargs.get(ATTR_EFFECT)) is not None:
            eff = effect_by_label(label, self._allow_flashing)
            if eff is None:
                raise HomeAssistantError(f"Unknown or disabled effect: {label}")
            effect_id = eff.id
        rgb = kwargs.get(ATTR_RGB_COLOR)
        bri = kwargs.get(ATTR_BRIGHTNESS)
        await self._device.async_command(
            on=True,
            rgb=tuple(rgb) if rgb is not None else None,
            effect_id=effect_id,
            brightness=_to_pct(bri) if bri is not None else None,
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._device.async_command(on=False)
