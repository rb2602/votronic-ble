"""Setup, unload, removal and entities created from received frames."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.votronic_ble.const import (
    DATA_TIMEOUT_SECONDS,
    DEFAULT_RECONNECT_SECONDS,
    DOMAIN,
)
from custom_components.votronic_ble.pairing import PairingError, PairingUnavailable

from helpers import make_client, make_entry

INIT = "custom_components.votronic_ble"
BLUETOOTH = "custom_components.votronic_ble.bluetooth"
ADDRESS = "AA:BB:CC:DD:EE:01"
# The frames of tests/test_parser.py, taken from syssi/esphome-votronic.
BATTERY_FRAME = bytes.fromhex("e804bf04090160005f009afefff00a5e14540204")
SOLAR_FRAME = bytes.fromhex("e8047605000000000006560009180022000000")
# The same frame with the controller in standby (status byte 12 is 0).
STANDBY_FRAME = SOLAR_FRAME[:12] + b"\x00" + SOLAR_FRAME[13:]


async def _setup(hass: HomeAssistant, client):
    entry = make_entry(1)
    entry.add_to_hass(hass)
    connect = AsyncMock(return_value=client)
    with patch(f"{BLUETOOTH}.establish_connection", connect):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done(wait_background_tasks=True)
    return entry, connect


def _connector(hass: HomeAssistant, entry) -> dr.DeviceEntry | None:
    # Looked up through the entry: the registry's lookup by identifier is
    # newer than the minimum Home Assistant version.
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    return next((d for d in devices if (DOMAIN, ADDRESS) in d.identifiers), None)


def _entity_id(hass: HomeAssistant, platform: str, key: str) -> str | None:
    return er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"{ADDRESS}_{key}")


async def test_setup_and_unload(hass: HomeAssistant, ble_device) -> None:
    client = make_client()
    entry, connect = await _setup(hass, client)

    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.connected
    connect.assert_awaited_once()
    assert client.start_notify.await_count == 2

    # Until the first frame arrives, the entry has no entities; the Bluetooth
    # Connector appears in the device registry with its first entities.
    assert not er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    assert _connector(hass, entry) is None

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert client.stop_notify.await_count == 2
    client.disconnect.assert_awaited()


async def test_setup_succeeds_while_device_is_out_of_range(hass: HomeAssistant) -> None:
    entry, connect = await _setup(hass, make_client())
    assert entry.state is ConfigEntryState.LOADED
    assert not entry.runtime_data.connected
    connect.assert_not_awaited()


async def test_setup_does_not_wait_for_the_connection(hass: HomeAssistant, ble_device) -> None:
    entry = make_entry(1)
    entry.add_to_hass(hass)
    client = make_client()
    answer = asyncio.Event()

    async def slow_connect(*args, **kwargs):
        await answer.wait()
        return client

    with patch(f"{BLUETOOTH}.establish_connection", side_effect=slow_connect):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.LOADED
        assert not entry.runtime_data.connected

        answer.set()
        await hass.async_block_till_done(wait_background_tasks=True)
    assert entry.runtime_data.connected


async def test_unload_while_connecting(hass: HomeAssistant, ble_device) -> None:
    entry = make_entry(1)
    entry.add_to_hass(hass)
    cancelled = asyncio.Event()

    async def endless_connect(*args, **kwargs):
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    with patch(f"{BLUETOOTH}.establish_connection", side_effect=endless_connect):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        device = entry.runtime_data
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done(wait_background_tasks=True)
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert cancelled.is_set()
    assert not device.connected


async def test_entities_appear_with_their_first_frame(hass: HomeAssistant, ble_device) -> None:
    entry, _ = await _setup(hass, make_client())
    device = entry.runtime_data

    device._battery_notification(None, bytearray(BATTERY_FRAME))
    await hass.async_block_till_done()
    connector = _connector(hass, entry)
    assert connector is not None
    assert connector.name == "Votronic S-BC EE01"
    assert ("bluetooth", ADDRESS) in connector.connections
    voltage = _entity_id(hass, "sensor", "battery_voltage")
    assert er.async_get(hass).async_get(voltage).device_id == connector.id
    assert float(hass.states.get(voltage).state) == 12.56
    assert float(hass.states.get(_entity_id(hass, "sensor", "state_of_charge")).state) == 95
    # Solar charger entities wait for a solar charger frame.
    assert _entity_id(hass, "sensor", "pv_voltage") is None

    device._solar_notification(None, bytearray(SOLAR_FRAME))
    await hass.async_block_till_done()
    assert float(hass.states.get(_entity_id(hass, "sensor", "pv_voltage")).state) == 13.98
    assert hass.states.get(_entity_id(hass, "sensor", "pv_controller_status")).state == "Active"
    assert hass.states.get(_entity_id(hass, "binary_sensor", "controller_active")).state == "on"


async def test_temperature_unknown_in_standby(hass: HomeAssistant, ble_device) -> None:
    entry, _ = await _setup(hass, make_client())
    entry.runtime_data._solar_notification(None, bytearray(STANDBY_FRAME))
    await hass.async_block_till_done()
    temperature = _entity_id(hass, "sensor", "pv_controller_temperature")
    assert hass.states.get(temperature).state == STATE_UNKNOWN
    assert hass.states.get(_entity_id(hass, "sensor", "pv_controller_status")).state == "Standby"
    assert float(hass.states.get(_entity_id(hass, "sensor", "pv_voltage")).state) == 13.98


async def test_invalid_frame_creates_no_entities(hass: HomeAssistant, ble_device) -> None:
    entry, _ = await _setup(hass, make_client())
    entry.runtime_data._battery_notification(None, bytearray(b"\x00\x01"))
    await hass.async_block_till_done()
    assert _entity_id(hass, "sensor", "battery_voltage") is None


async def test_entities_unavailable_while_disconnected(hass: HomeAssistant, ble_device) -> None:
    client = make_client()
    entry, connect = await _setup(hass, client)
    entry.runtime_data._battery_notification(None, bytearray(BATTERY_FRAME))
    await hass.async_block_till_done()
    voltage = _entity_id(hass, "sensor", "battery_voltage")

    connect.call_args.kwargs["disconnected_callback"](client)
    await hass.async_block_till_done()
    assert hass.states.get(voltage).state == STATE_UNAVAILABLE


async def test_values_need_a_new_frame_after_reconnect(hass: HomeAssistant, ble_device) -> None:
    first, second = make_client(), make_client()
    entry = make_entry(1)
    entry.add_to_hass(hass)
    connect = AsyncMock(side_effect=[first, second])
    with patch(f"{BLUETOOTH}.establish_connection", connect):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done(wait_background_tasks=True)
        device = entry.runtime_data
        device._battery_notification(None, bytearray(BATTERY_FRAME))
        await hass.async_block_till_done()
        voltage = _entity_id(hass, "sensor", "battery_voltage")

        connect.call_args.kwargs["disconnected_callback"](first)
        await hass.async_block_till_done()
        async_fire_time_changed(
            hass, dt_util.utcnow() + timedelta(seconds=DEFAULT_RECONNECT_SECONDS + 1)
        )
        await hass.async_block_till_done()

    assert device.connected
    assert hass.states.get(voltage).state == STATE_UNAVAILABLE
    device._battery_notification(None, bytearray(BATTERY_FRAME))
    await hass.async_block_till_done()
    assert float(hass.states.get(voltage).state) == 12.56


async def test_values_unavailable_without_frames(
    hass: HomeAssistant, ble_device, freezer: FrozenDateTimeFactory
) -> None:
    entry, _ = await _setup(hass, make_client())
    device = entry.runtime_data
    device._battery_notification(None, bytearray(BATTERY_FRAME))
    device._solar_notification(None, bytearray(SOLAR_FRAME))
    await hass.async_block_till_done()
    voltage = _entity_id(hass, "sensor", "battery_voltage")
    pv_voltage = _entity_id(hass, "sensor", "pv_voltage")

    # The solar charger stops sending; the battery computer goes on.
    for _ in range(DATA_TIMEOUT_SECONDS // 5 + 1):
        freezer.tick(timedelta(seconds=5))
        device._battery_notification(None, bytearray(BATTERY_FRAME))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
    assert hass.states.get(pv_voltage).state == STATE_UNAVAILABLE
    # Battery voltage comes from both devices, so the battery computer keeps it.
    assert float(hass.states.get(voltage).state) == 12.56

    device._solar_notification(None, bytearray(SOLAR_FRAME))
    await hass.async_block_till_done()
    assert float(hass.states.get(pv_voltage).state) == 13.98


async def test_removal_removes_the_pairing(hass: HomeAssistant) -> None:
    entry, _ = await _setup(hass, make_client())
    with patch(f"{INIT}.async_remove_pairings", AsyncMock()) as remove:
        await hass.config_entries.async_remove(entry.entry_id)
    remove.assert_awaited_once_with(ADDRESS)
    assert hass.config_entries.async_get_entry(entry.entry_id) is None


@pytest.mark.parametrize("error", [PairingError("refused"), PairingUnavailable("no bus")])
async def test_removal_succeeds_when_the_pairing_stays(hass: HomeAssistant, error) -> None:
    entry, _ = await _setup(hass, make_client())
    with patch(f"{INIT}.async_remove_pairings", AsyncMock(side_effect=error)):
        await hass.config_entries.async_remove(entry.entry_id)
    assert hass.config_entries.async_get_entry(entry.entry_id) is None
