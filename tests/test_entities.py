import json
from pathlib import Path

import pytest
from homeassistant.components.light import ATTR_EFFECT, ATTR_EFFECT_LIST
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry, mock_restore_cache, State

from custom_components.duoco_stripx.const import CONF_ADDRESS, CONF_NAME, DOMAIN
from .conftest import ADDR, ADDR2, FakeClient

LIGHT = "light.strip"
SPEED = "number.strip_effect_speed"


async def _setup(hass, name="Strip", addr=ADDR, options=None):
    e = MockConfigEntry(domain=DOMAIN, unique_id=addr, title=name, data={CONF_ADDRESS: addr, CONF_NAME: name, "firmware": "fw"}, options=options or {})
    e.add_to_hass(hass)
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    return e


async def test_no_flash_on_startup_and_unknown_assumed_state(hass, ble):
    await _setup(hass)
    assert ble.establish.call_count == 0
    s = hass.states.get(LIGHT)
    assert s.state == STATE_UNKNOWN
    assert s.attributes["assumed_state"] is True
    assert hass.states.get(SPEED).state == STATE_UNKNOWN


async def test_turn_on_with_color_brightness_preserves(hass, ble):
    await _setup(hass)
    await hass.services.async_call("light", "turn_on", {"entity_id": LIGHT, "rgb_color": [255, 0, 0], "brightness": 128}, blocking=True)
    c = FakeClient.instances[-1]
    assert [w[1].hex() for w in c.writes] == ["7e0404010001ff00ef", "7e070503ff000010ef", "7e040132ffffff00ef"]
    s = hass.states.get(LIGHT)
    assert s.state == STATE_ON and s.attributes["rgb_color"] == (255, 0, 0) and s.attributes["brightness"] == 128
    await hass.services.async_call("light", "turn_on", {"entity_id": LIGHT, "brightness": 255}, blocking=True)
    s = hass.states.get(LIGHT)
    assert s.attributes["rgb_color"] == (255, 0, 0) and s.attributes["brightness"] == 255
    assert FakeClient.instances[-1].writes[-1][1].hex() == "7e040164ffffff00ef"


async def test_turn_off(hass, ble):
    await _setup(hass)
    await hass.services.async_call("light", "turn_off", {"entity_id": LIGHT}, blocking=True)
    assert FakeClient.instances[-1].writes[0][1].hex() == "7e0404000000ff00ef"
    assert hass.states.get(LIGHT).state == STATE_OFF


async def test_effect_list_excludes_strobe_and_scenes_by_default(hass, ble):
    await _setup(hass)
    lst = hass.states.get(LIGHT).attributes[ATTR_EFFECT_LIST]
    assert "Auto Play" in lst and "7-Color Strobe" not in lst and len(lst) == 210


async def test_flashing_option_exposes_strobe(hass, ble):
    await _setup(hass, options={"allow_flashing_effects": True})
    lst = hass.states.get(LIGHT).attributes[ATTR_EFFECT_LIST]
    assert "7-Color Strobe" in lst and len(lst) == 213


async def test_set_effect_and_unknown_effect_rejected(hass, ble):
    await _setup(hass)
    await hass.services.async_call("light", "turn_on", {"entity_id": LIGHT, "effect": "7-Color Energy"}, blocking=True)
    assert FakeClient.instances[-1].writes[-1][1].hex() == "7e0503d406ffff00ef"
    assert hass.states.get(LIGHT).attributes[ATTR_EFFECT] == "7-Color Energy"
    n = len(FakeClient.instances)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call("light", "turn_on", {"entity_id": LIGHT, "effect": "7-Color Strobe"}, blocking=True)
    assert len(FakeClient.instances) == n


async def test_speed_number_writes_only_speed_and_keeps_light_state(hass, ble):
    await _setup(hass)
    await hass.services.async_call("light", "turn_on", {"entity_id": LIGHT, "effect": "Auto Play"}, blocking=True)
    await hass.services.async_call("number", "set_value", {"entity_id": SPEED, "value": 40}, blocking=True)
    c = FakeClient.instances[-1]
    assert [w[1].hex() for w in c.writes] == ["7e040228ffffff00ef"]
    assert float(hass.states.get(SPEED).state) == 40
    assert hass.states.get(LIGHT).attributes[ATTR_EFFECT] == "Auto Play"
    with pytest.raises(Exception):
        await hass.services.async_call("number", "set_value", {"entity_id": SPEED, "value": 101}, blocking=True)


async def test_failure_marks_unavailable_not_applied(hass, ble):
    await _setup(hass)
    ble.connect_error = TimeoutError()
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call("light", "turn_on", {"entity_id": LIGHT}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get(LIGHT).state == STATE_UNAVAILABLE


async def test_unavailable_when_not_advertising_then_recovers(hass, ble):
    ble.present = False
    await _setup(hass)
    assert hass.states.get(LIGHT).state == STATE_UNAVAILABLE
    ble.cbs["seen"](object(), object())
    await hass.async_block_till_done()
    assert hass.states.get(LIGHT).state == STATE_UNKNOWN


async def test_restore_state_without_writes(hass, ble):
    reg_id = "AA:BB:CC:00:00:01_light"
    mock_restore_cache(hass, [
        State(LIGHT, STATE_ON, {"rgb_color": (1, 2, 3), "brightness": 128, "effect": None}),
        State(SPEED, "33"),
    ])
    await _setup(hass)
    assert ble.establish.call_count == 0
    s = hass.states.get(LIGHT)
    # restored values are diagnostic only: state stays unknown until a command is sent
    assert s.state == STATE_UNKNOWN and s.attributes["assumed_state"] is True
    assert s.attributes.get("rgb_color") is None
    assert s.attributes["last_known_rgb_color"] == (1, 2, 3)
    assert s.attributes["last_known_brightness"] == 128
    assert s.attributes["last_known_state"] == STATE_ON
    n = hass.states.get(SPEED)
    assert n.state == STATE_UNKNOWN and n.attributes["last_known_value"] == 33


async def test_multi_device_independent(hass, ble):
    await _setup(hass, "Strip", ADDR)
    await _setup(hass, "Other", ADDR2)
    await hass.services.async_call("light", "turn_on", {"entity_id": LIGHT, "rgb_color": [9, 9, 9]}, blocking=True)
    assert hass.states.get("light.other").state == STATE_UNKNOWN


async def test_unload_cleans_up(hass, ble):
    e = await _setup(hass)
    assert await hass.config_entries.async_unload(e.entry_id)
    await hass.async_block_till_done()
    assert ble.cbs == {}
    assert hass.states.get(LIGHT).state == STATE_UNAVAILABLE


def test_metadata_valid():
    root = Path(__file__).parent.parent
    m = json.loads((root / "custom_components/duoco_stripx/manifest.json").read_text())
    assert m["domain"] == "duoco_stripx" and m["version"] == "0.1.0"
    assert m["codeowners"] == ["@tgmstudios"] and m["config_flow"] is True
    assert m["iot_class"] == "assumed_state"
    assert m["bluetooth"] == [{"local_name": "MELK-OA21*", "connectable": True}]
    assert "bluetooth" in m["dependencies"]
    h = json.loads((root / "hacs.json").read_text())
    assert h["name"] and h["homeassistant"]
    s = json.loads((root / "custom_components/duoco_stripx/strings.json").read_text())
    t = json.loads((root / "custom_components/duoco_stripx/translations/en.json").read_text())
    assert s == t
    assert not (root / "LICENSE").exists()
