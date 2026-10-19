from __future__ import annotations

import re
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak

from .const import (
    CONF_ADDRESS,
    CONF_FIRMWARE,
    CONF_NAME,
    CONF_OWNED,
    DOMAIN,
    NAME_PATTERN,
    OPT_ALLOW_FLASHING,
)
from .device import async_read_firmware

_MAC = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$")


class DuoCoConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._discovered: BluetoothServiceInfoBleak | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return DuoCoOptionsFlow()

    def _name_taken(self, name: str) -> bool:
        return any(e.title.casefold() == name.casefold() for e in self._async_current_entries())

    async def _validate(self, address: str, name: str, owned: bool) -> tuple[dict[str, str], str]:
        errors: dict[str, str] = {}
        if not name:
            errors[CONF_NAME] = "invalid_name"
        elif self._name_taken(name):
            errors[CONF_NAME] = "name_exists"
        if not owned:
            errors[CONF_OWNED] = "ownership_required"
        if errors:
            return errors, ""
        try:
            return {}, await async_read_firmware(self.hass, address)  # read-only, no writes
        except HomeAssistantError:
            return {"base": "cannot_connect"}, ""

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            raw = user_input[CONF_ADDRESS].strip()
            name = user_input[CONF_NAME].strip()
            if not _MAC.match(raw):
                errors[CONF_ADDRESS] = "invalid_address"
            else:
                address = raw.upper().replace("-", ":")
                await self.async_set_unique_id(address)
                self._abort_if_unique_id_configured()
                errors, fw = await self._validate(address, name, user_input[CONF_OWNED])
                if not errors:
                    return self.async_create_entry(
                        title=name, data={CONF_ADDRESS: address, CONF_NAME: name, CONF_FIRMWARE: fw}
                    )
        schema = vol.Schema(
            {
                vol.Required(CONF_ADDRESS, default=(user_input or {}).get(CONF_ADDRESS, "")): str,
                vol.Required(CONF_NAME, default=(user_input or {}).get(CONF_NAME, "DuoCo StripX")): str,
                vol.Required(CONF_OWNED, default=False): bool,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_bluetooth(self, discovery_info: BluetoothServiceInfoBleak) -> ConfigFlowResult:
        if not re.match(NAME_PATTERN, discovery_info.name or ""):
            return self.async_abort(reason="not_supported")
        await self.async_set_unique_id(discovery_info.address.upper())
        self._abort_if_unique_id_configured()
        self._discovered = discovery_info
        self.context["title_placeholders"] = {"name": "DuoCo StripX"}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        assert self._discovered is not None
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            errs, fw = await self._validate(self._discovered.address.upper(), name, user_input[CONF_OWNED])
            if not errs:
                return self.async_create_entry(
                    title=name,
                    data={CONF_ADDRESS: self._discovered.address.upper(), CONF_NAME: name, CONF_FIRMWARE: fw},
                )
            errors = errs
        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default="DuoCo StripX"): str,
                vol.Required(CONF_OWNED, default=False): bool,
            }
        )
        return self.async_show_form(step_id="bluetooth_confirm", data_schema=schema, errors=errors)


class DuoCoOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        cur = self.config_entry.options.get(OPT_ALLOW_FLASHING, False)
        return self.async_show_form(
            step_id="init", data_schema=vol.Schema({vol.Required(OPT_ALLOW_FLASHING, default=cur): bool})
        )
