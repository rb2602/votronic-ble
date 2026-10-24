"""Bluetooth connection handling for Votronic devices."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime, timedelta
import logging
from typing import Any

from bleak import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
from homeassistant.components import bluetooth
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import (
    CHAR_BATTERY_COMPUTER_UUID,
    CHAR_SOLAR_CHARGER_UUID,
    DATA_TIMEOUT_SECONDS,
    DEFAULT_RECONNECT_SECONDS,
)
from .parser import (
    FrameType,
    ParsedFrame,
    VotronicFrameError,
    frame_types_for_key,
    parse_battery_computer,
    parse_solar_charger,
)

_LOGGER = logging.getLogger(__name__)

DATA_TIMEOUT = timedelta(seconds=DATA_TIMEOUT_SECONDS)
STALE_CHECK_INTERVAL = timedelta(seconds=5)


class VotronicBluetoothDevice:
    """Manage one Votronic Bluetooth connection."""

    def __init__(self, hass: HomeAssistant, address: str, name: str) -> None:
        """Initialize the Bluetooth device."""

        self.hass = hass
        self.address = address.upper()
        self.name = name

        self._client: BleakClientWithServiceCache | None = None
        # Serializes start and reconnect attempts so two connections are
        # never established at the same time.
        self._connect_lock = asyncio.Lock()
        self._connected = False
        self._closing = False
        self._reconnect_cancel: CALLBACK_TYPE | None = None
        # Set after the first failed connect of an outage, so a device that
        # stays out of reach logs one warning, not one per reconnect attempt.
        self._connect_failure_logged = False
        self._listeners: set[Callable[[], None]] = set()
        self._values: dict[str, Any] = {}
        self.seen_frame_types: set[FrameType] = set()
        # When the last frame of each type arrived on the current connection,
        # and the types without a frame for DATA_TIMEOUT, see is_current.
        self._frame_times: dict[FrameType, datetime] = {}
        self._stale_frame_types: set[FrameType] = set()
        self._stale_check_cancel: CALLBACK_TYPE | None = None

    @property
    def connected(self) -> bool:
        """Return connection state."""

        return self._connected

    def get_value(self, key: str) -> Any:
        """Return the latest value for a key."""

        return self._values.get(key)

    def is_current(self, key: str) -> bool:
        """Return if a frame with the key arrived on this connection lately."""

        limit = dt_util.utcnow() - DATA_TIMEOUT
        return any(
            self._frame_times.get(frame_type, limit) > limit
            for frame_type in frame_types_for_key(key)
        )

    @callback
    def async_subscribe(self, listener: Callable[[], None]) -> CALLBACK_TYPE:
        """Subscribe to value changes."""

        self._listeners.add(listener)

        @callback
        def _unsubscribe() -> None:
            self._listeners.discard(listener)

        return _unsubscribe

    async def async_start(self) -> None:
        """Start the Bluetooth connection."""

        if self._closing:
            return
        self._stale_check_cancel = async_track_time_interval(
            self.hass, self._check_stale, STALE_CHECK_INTERVAL
        )
        await self._async_connect()

    async def async_stop(self) -> None:
        """Stop the Bluetooth connection."""

        self._closing = True
        if self._reconnect_cancel is not None:
            self._reconnect_cancel()
            self._reconnect_cancel = None
        if self._stale_check_cancel is not None:
            self._stale_check_cancel()
            self._stale_check_cancel = None

        client = self._client
        self._client = None
        if client and client.is_connected:
            with suppress(BleakError, asyncio.TimeoutError):
                await client.stop_notify(CHAR_BATTERY_COMPUTER_UUID)
            with suppress(BleakError, asyncio.TimeoutError):
                await client.stop_notify(CHAR_SOLAR_CHARGER_UUID)
            with suppress(BleakError, asyncio.TimeoutError):
                await client.disconnect()

        self._set_connected(False)

    async def _async_connect(self) -> None:
        """Connect and subscribe to notifications."""

        async with self._connect_lock:
            await self._async_connect_locked()

    async def _async_connect_locked(self) -> None:
        if self._closing:
            return
        if self._client is not None and self._client.is_connected:
            return

        ble_device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if ble_device is None:
            _LOGGER.debug("Votronic device %s is not currently discoverable", self.address)
            self._schedule_reconnect()
            return

        client: BleakClientWithServiceCache | None = None
        try:
            client = await establish_connection(
                BleakClientWithServiceCache,
                ble_device,
                self.name,
                disconnected_callback=self._disconnected,
            )
            # Publish the client before subscribing so a disconnect during
            # start_notify is attributed to this connection.
            self._client = client
            services = client.services
            subscribed = False
            if services.get_characteristic(CHAR_BATTERY_COMPUTER_UUID) is not None:
                await client.start_notify(CHAR_BATTERY_COMPUTER_UUID, self._battery_notification)
                subscribed = True
            if services.get_characteristic(CHAR_SOLAR_CHARGER_UUID) is not None:
                await client.start_notify(CHAR_SOLAR_CHARGER_UUID, self._solar_notification)
                subscribed = True
            if not subscribed:
                raise BleakError("No Votronic monitoring characteristics found")
        except (TimeoutError, BleakError) as err:
            if self._connect_failure_logged:
                _LOGGER.debug("Could not connect to Votronic device %s: %s", self.address, err)
            else:
                _LOGGER.warning(
                    "Could not connect to Votronic device %s: %s. Retrying every %s seconds",
                    self.address,
                    err,
                    DEFAULT_RECONNECT_SECONDS,
                )
                self._connect_failure_logged = True
            self._client = None
            if client is not None:
                with suppress(BleakError, asyncio.TimeoutError):
                    await client.disconnect()
            self._schedule_reconnect()
            return

        if self._closing:
            # async_stop ran while we were connecting.
            self._client = None
            with suppress(BleakError, asyncio.TimeoutError):
                await client.disconnect()
            return

        if self._client is not client or not client.is_connected:
            # The connection dropped during start_notify; _handle_disconnect
            # may already have cleared the client and scheduled the reconnect.
            _LOGGER.debug("Votronic device %s disconnected while subscribing", self.address)
            self._client = None
            self._schedule_reconnect()
            return

        if self._connect_failure_logged:
            _LOGGER.info("Connected to Votronic device %s again", self.address)
            self._connect_failure_logged = False
        self._set_connected(True)

    def _disconnected(self, client: BleakClientWithServiceCache) -> None:
        """Handle Bluetooth disconnects."""

        self.hass.loop.call_soon_threadsafe(self._handle_disconnect, client)

    @callback
    def _handle_disconnect(self, client: BleakClientWithServiceCache) -> None:
        if client is not self._client:
            # A late callback from a connection that was already replaced or
            # closed. Acting on it would tear down the current connection.
            _LOGGER.debug("Ignoring disconnect of a stale client for %s", self.address)
            return
        self._set_connected(False)
        self._client = None
        self._schedule_reconnect()

    @callback
    def _schedule_reconnect(self) -> None:
        if self._closing or self._reconnect_cancel is not None:
            return

        async def _reconnect(_now: Any) -> None:
            self._reconnect_cancel = None
            await self._async_connect()

        self._reconnect_cancel = async_call_later(self.hass, DEFAULT_RECONNECT_SECONDS, _reconnect)

    def _battery_notification(self, _sender: Any, data: bytearray) -> None:
        self.hass.loop.call_soon_threadsafe(self._handle_battery_data, bytes(data))

    def _solar_notification(self, _sender: Any, data: bytearray) -> None:
        self.hass.loop.call_soon_threadsafe(self._handle_solar_data, bytes(data))

    @callback
    def _handle_battery_data(self, data: bytes) -> None:
        try:
            frame = parse_battery_computer(data)
        except VotronicFrameError as err:
            _LOGGER.debug("Ignoring invalid Votronic battery frame: %s", err)
            return
        self._update_values(frame)

    @callback
    def _handle_solar_data(self, data: bytes) -> None:
        try:
            frame = parse_solar_charger(data)
        except VotronicFrameError as err:
            _LOGGER.debug("Ignoring invalid Votronic solar frame: %s", err)
            return
        self._update_values(frame)

    @callback
    def _update_values(self, frame: ParsedFrame) -> None:
        self.seen_frame_types.add(frame.frame_type)
        self._frame_times[frame.frame_type] = dt_util.utcnow()
        self._stale_frame_types.discard(frame.frame_type)
        self._values.update(frame.values)
        self._notify_listeners()

    @callback
    def _check_stale(self, _now: datetime) -> None:
        """Make values unavailable whose frames stopped, see is_current."""

        limit = dt_util.utcnow() - DATA_TIMEOUT
        stale = {
            frame_type for frame_type, received in self._frame_times.items() if received <= limit
        }
        if stale == self._stale_frame_types:
            return
        for frame_type in stale - self._stale_frame_types:
            _LOGGER.debug(
                "No %s frame from %s for %s seconds",
                frame_type.value,
                self.address,
                DATA_TIMEOUT_SECONDS,
            )
        self._stale_frame_types = stale
        self._notify_listeners()

    @callback
    def _set_connected(self, connected: bool) -> None:
        if not connected:
            # Values need a new frame after a reconnect, see is_current.
            self._frame_times.clear()
            self._stale_frame_types.clear()
        if self._connected == connected:
            return
        self._connected = connected
        self._notify_listeners()

    @callback
    def _notify_listeners(self) -> None:
        # Iterate over a snapshot: a listener may add entities, and Home
        # Assistant starts that task eagerly, so their async_added_to_hass
        # subscribes new listeners while this loop is still running.
        for listener in list(self._listeners):
            listener()
