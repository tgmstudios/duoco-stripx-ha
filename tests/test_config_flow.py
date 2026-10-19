from unittest.mock import patch

from homeassistant import config_entries, data_entry_flow
from homeassistant.exceptions import HomeAssistantError
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.duoco_stripx.const import CONF_ADDRESS, CONF_NAME, CONF_OWNED, DOMAIN
from .conftest import ADDR, ADDR2

RF = "custom_components.duoco_stripx.config_flow.async_read_firmware"


async def _start(hass):
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})


async def test_manual_success(hass):
    r = await _start(hass)
    assert r["type"] is data_entry_flow.FlowResultType.FORM
    with patch(RF, return_value="P30V32") as rf, patch("custom_components.duoco_stripx.async_setup_entry", return_value=True):
        r = await hass.config_entries.flow.async_configure(
            r["flow_id"], {CONF_ADDRESS: ADDR.lower(), CONF_NAME: " Strip ", CONF_OWNED: True}
        )
    assert r["type"] is data_entry_flow.FlowResultType.CREATE_ENTRY
    assert r["title"] == "Strip"
    assert r["data"][CONF_ADDRESS] == ADDR and r["data"]["firmware"] == "P30V32"
    rf.assert_awaited_once()


async def test_invalid_address_and_name(hass):
    r = await _start(hass)
    for addr, name, err in [("nonsense", "x", "invalid_address"), (ADDR, "   ", "invalid_name")]:
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_ADDRESS: addr, CONF_NAME: name, CONF_OWNED: True})
        assert r["type"] is data_entry_flow.FlowResultType.FORM
        assert err in r["errors"].values()


async def test_ownership_required(hass):
    r = await _start(hass)
    with patch(RF) as rf:
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_ADDRESS: ADDR, CONF_NAME: "x", CONF_OWNED: False})
    assert "ownership_required" in r["errors"].values()
    rf.assert_not_called()


async def test_duplicate_address_and_name(hass):
    MockConfigEntry(domain=DOMAIN, unique_id=ADDR, title="Taken", data={CONF_ADDRESS: ADDR, CONF_NAME: "Taken"}).add_to_hass(hass)
    r = await _start(hass)
    with patch(RF, return_value=""):
        r2 = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_ADDRESS: ADDR, CONF_NAME: "Other", CONF_OWNED: True})
    assert r2["type"] is data_entry_flow.FlowResultType.ABORT and r2["reason"] == "already_configured"
    r = await _start(hass)
    with patch(RF, return_value=""):
        r3 = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_ADDRESS: ADDR2, CONF_NAME: "taken", CONF_OWNED: True})
    assert "name_exists" in r3["errors"].values()


async def test_cannot_connect(hass):
    r = await _start(hass)
    with patch(RF, side_effect=HomeAssistantError("nope")):
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_ADDRESS: ADDR, CONF_NAME: "x", CONF_OWNED: True})
    assert r["type"] is data_entry_flow.FlowResultType.FORM and "cannot_connect" in r["errors"].values()


def _info(name, addr=ADDR):
    return BluetoothServiceInfoBleak(
        name=name, address=addr, rssi=-50, manufacturer_data={}, service_data={}, service_uuids=[],
        source="local", device=__import__("unittest.mock").mock.MagicMock(), advertisement=__import__("unittest.mock").mock.MagicMock(),
        connectable=True, time=0, tx_power=None,
    )


async def test_bluetooth_discovery_requires_confirmation_and_no_writes(hass):
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_BLUETOOTH}, data=_info("MELK-OA21 1234"))
    assert r["type"] is data_entry_flow.FlowResultType.FORM and r["step_id"] == "bluetooth_confirm"
    assert hass.config_entries.async_entries(DOMAIN) == []
    with patch(RF, return_value="fw"), patch("custom_components.duoco_stripx.async_setup_entry", return_value=True):
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_NAME: "Strip", CONF_OWNED: True})
    assert r["type"] is data_entry_flow.FlowResultType.CREATE_ENTRY


async def test_bluetooth_discovery_rejects_other_families(hass):
    for n in ("MELK-OB21", "ELK-BLEDOM01", "MELK-OC21", None):
        r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_BLUETOOTH}, data=_info(n))
        assert r["type"] is data_entry_flow.FlowResultType.ABORT and r["reason"] == "not_supported"


async def test_options_flow_flashing(hass):
    e = MockConfigEntry(domain=DOMAIN, unique_id=ADDR, data={CONF_ADDRESS: ADDR, CONF_NAME: "x"})
    e.add_to_hass(hass)
    r = await hass.config_entries.options.async_init(e.entry_id)
    assert r["type"] is data_entry_flow.FlowResultType.FORM
    r = await hass.config_entries.options.async_configure(r["flow_id"], {"allow_flashing_effects": True})
    assert r["data"] == {"allow_flashing_effects": True}
