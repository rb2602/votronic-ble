"""Bluetooth reconnects and their logging."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from unittest.mock import AsyncMock, patch

from bleak import BleakError
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.votronic_ble.const import (
    CHAR_BATTERY_COMPUTER_UUID,
    DEFAULT_RECONNECT_SECONDS,
)

from helpers import make_client, make_entry

BLUETOOTH = "custom_components.votronic_ble.bluetooth"


def _messages(caplog: pytest.LogCaptureFixture, level: int, prefix: str = "") -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.name == BLUETOOTH
        and record.levelno == level
        and record.getMessage().startswith(prefix)
    ]


async def _wait_for_reconnects(hass: HomeAssistant, count: int) -> None:
    now = dt_util.utcnow()
    for step in range(1, count + 1):
        async_fire_time_changed(
            hass, now + timedelta(seconds=(DEFAULT_RECONNECT_SECONDS + 1) * step)
        )
        await hass.async_block_till_done()


async def test_one_warning_per_outage(
    hass: HomeAssistant, ble_device, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger=BLUETOOTH)
    entry = make_entry(1)
    entry.add_to_hass(hass)
    connect = AsyncMock(side_effect=BleakError("out of range"))
    with patch(f"{BLUETOOTH}.establish_connection", connect):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done(wait_background_tasks=True)
        await _wait_for_reconnects(hass, 4)
        assert connect.await_count == 5
        assert len(_messages(caplog, logging.WARNING)) == 1
        assert len(_messages(caplog, logging.DEBUG, "Could not connect")) == 4

        connect.side_effect = None
        connect.return_value = make_client()
        await _wait_for_reconnects(hass, 1)

    assert entry.runtime_data.connected
    assert _messages(caplog, logging.INFO) == [
        "Connected to Votronic device AA:BB:CC:DD:EE:01 again"
    ]


async def test_reconnects_after_disconnect(hass: HomeAssistant, ble_device) -> None:
    entry = make_entry(1)
    entry.add_to_hass(hass)
    first, second = make_client(), make_client()
    connect = AsyncMock(side_effect=[first, second])
    with patch(f"{BLUETOOTH}.establish_connection", connect):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done(wait_background_tasks=True)
        device = entry.runtime_data

        connect.call_args.kwargs["disconnected_callback"](first)
        await hass.async_block_till_done()
        assert not device.connected

        await _wait_for_reconnects(hass, 1)
    assert device.connected
    assert connect.await_count == 2


async def test_disconnect_between_subscriptions(hass: HomeAssistant, ble_device) -> None:
    entry = make_entry(1)
    entry.add_to_hass(hass)
    first, second = make_client(), make_client()
    connect = AsyncMock(side_effect=[first, second])

    async def drop_after_battery_subscription(uuid: str, _callback) -> None:
        if uuid == CHAR_BATTERY_COMPUTER_UUID:
            first.is_connected = False
            connect.call_args.kwargs["disconnected_callback"](first)
            await asyncio.sleep(0)  # The disconnect is handled before the next subscription.

    first.start_notify.side_effect = drop_after_battery_subscription
    with patch(f"{BLUETOOTH}.establish_connection", connect):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done(wait_background_tasks=True)
        device = entry.runtime_data
        assert first.start_notify.await_count == 2
        assert not device.connected

        await _wait_for_reconnects(hass, 1)
    assert device.connected
    assert connect.await_count == 2


async def test_ignores_disconnect_of_replaced_client(hass: HomeAssistant, ble_device) -> None:
    entry = make_entry(1)
    entry.add_to_hass(hass)
    client = make_client()
    connect = AsyncMock(return_value=client)
    with patch(f"{BLUETOOTH}.establish_connection", connect):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done(wait_background_tasks=True)

    connect.call_args.kwargs["disconnected_callback"](make_client())
    await hass.async_block_till_done()
    assert entry.runtime_data.connected


async def test_device_without_notification_characteristics(hass: HomeAssistant, ble_device) -> None:
    entry = make_entry(1)
    entry.add_to_hass(hass)
    client = make_client(())
    with patch(f"{BLUETOOTH}.establish_connection", AsyncMock(return_value=client)):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done(wait_background_tasks=True)
    assert not entry.runtime_data.connected
    client.disconnect.assert_awaited()
