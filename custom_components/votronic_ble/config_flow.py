"""Config flow for Votronic."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from contextlib import suppress
import logging
import re
from typing import Any

from bleak import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
from homeassistant import config_entries
from homeassistant.components import bluetooth
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.data_entry_flow import FlowResult
import voluptuous as vol

from .const import (
    CHAR_BATTERY_COMPUTER_UUID,
    CHAR_SOLAR_CHARGER_UUID,
    CONF_PAIRING_CODE,
    DEFAULT_PAIRING_CODE,
    DEVICE_NAME_PREFIX,
    DOMAIN,
    SERVICE_MONITORING_UUID,
    VOTRONIC_NAME_PREFIX,
)
from .pairing import (
    PairingError,
    PairingNotAccepted,
    PairingUnavailable,
    WrongPasskey,
    async_pair,
    async_prefer_le,
    async_reset_pairing,
)

_LOGGER = logging.getLogger(__name__)

PAIRING_CODE_PATTERN = re.compile(r"\d{6}")


def _device_name(address: str) -> str:
    """Return the device name, e.g. Votronic S-BC EEFF for AA:BB:CC:DD:EE:FF.

    The connector reports "Votronic" or, once BlueZ has read its GATT name,
    "Energy Monitor EEFF"; a name from the address does not change.
    """

    return f"{DEVICE_NAME_PREFIX} {address.replace(':', '')[-4:].upper()}"


def _normalize_address(address: str) -> str:
    """Normalize Bluetooth addresses for config entries and entity unique IDs."""

    return address.upper()


def _looks_like_votronic(service_info: bluetooth.BluetoothServiceInfoBleak) -> bool:
    name = (service_info.name or "").lower()
    service_uuids = {uuid.lower() for uuid in service_info.service_uuids}
    return name.startswith(VOTRONIC_NAME_PREFIX) or SERVICE_MONITORING_UUID in service_uuids


async def _validate_pairing(
    hass,
    address: str,
    pairing_code: int = DEFAULT_PAIRING_CODE,
) -> None:
    """Try to pair and verify the required notification characteristics exist."""

    ble_device = bluetooth.async_ble_device_from_address(hass, address, connectable=True)
    if ble_device is None:
        raise CannotConnect

    client: BleakClientWithServiceCache | None = None
    try:
        await async_reset_pairing(ble_device)
        await async_prefer_le(ble_device)
        client = await establish_connection(
            BleakClientWithServiceCache,
            ble_device,
            ble_device.name or address,
        )
        await _pair(client, ble_device, pairing_code)
        services = client.services
        if (
            services.get_characteristic(CHAR_BATTERY_COMPUTER_UUID) is None
            and services.get_characteristic(CHAR_SOLAR_CHARGER_UUID) is None
        ):
            raise UnsupportedDevice
    except PairingFailed, PairingNotAccepted, WrongPasskey:
        raise
    except (TimeoutError, BleakError, PairingError) as err:
        _LOGGER.debug(
            "Pairing validation failed for %s: %s",
            address,
            err,
        )
        raise CannotConnect from err
    finally:
        if client is not None:
            with suppress(BleakError, asyncio.TimeoutError):
                await client.disconnect()


async def _pair(client: BleakClientWithServiceCache, ble_device, pairing_code: int) -> None:
    """Pair through BlueZ with the pairing code, see pairing.py.

    A device behind a Bluetooth proxy falls back to the pairing of its
    backend, which cannot enter a pairing code. A backend without pairing
    fails too: without a pairing the Bluetooth Connector sends no data.
    """

    try:
        await async_pair(ble_device, pairing_code)
    except PairingUnavailable as unavailable:
        _LOGGER.debug("Pairing %s through its backend: %s", ble_device.address, unavailable)
        try:
            await client.pair()
        except (NotImplementedError, BleakError) as err:
            raise PairingFailed from err


class VotronicConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Votronic."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""

        self._discovered_device: bluetooth.BluetoothServiceInfoBleak | None = None
        self._discovered: dict[str, bluetooth.BluetoothServiceInfoBleak] = {}

    async def async_step_bluetooth(
        self, discovery_info: bluetooth.BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Handle Bluetooth discovery."""

        if not _looks_like_votronic(discovery_info):
            return self.async_abort(reason="not_supported")

        address = _normalize_address(discovery_info.address)
        await self.async_set_unique_id(address)
        self._abort_if_unique_id_configured()
        self._discovered_device = discovery_info
        self.context["title_placeholders"] = {
            "name": _device_name(address),
        }
        return await self.async_step_pair()

    async def async_step_user(self, user_input: Mapping[str, Any] | None = None) -> FlowResult:
        """Handle the user initiated flow."""

        errors: dict[str, str] = {}
        self._discovered = {
            _normalize_address(info.address): info
            for info in bluetooth.async_discovered_service_info(self.hass, connectable=True)
            if _looks_like_votronic(info)
        }

        if user_input is not None:
            address = _normalize_address(user_input[CONF_ADDRESS])
            info = self._discovered.get(address)
            if info is None:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(address)
                self._abort_if_unique_id_configured()
                self._discovered_device = info
                return await self.async_step_pair()

        if not self._discovered:
            return self.async_show_form(
                step_id="user",
                errors={"base": "no_devices_found"},
                data_schema=vol.Schema({}),
            )

        return self.async_show_form(
            step_id="user",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(
                        {
                            address: f"{_device_name(address)} ({address})"
                            for address in self._discovered
                        }
                    )
                }
            ),
        )

    async def async_step_pair(self, user_input: Mapping[str, Any] | None = None) -> FlowResult:
        """Guide the user through pressing the hardware pairing button."""

        if self._discovered_device is None:
            return await self.async_step_user()

        errors: dict[str, str] = {}
        if user_input is not None:
            error = await self._async_try_pairing(DEFAULT_PAIRING_CODE)
            if error is None:
                return await self._async_create_votronic_entry()
            if error == "wrong_pairing_code":
                # A user pairing code replaces the default one.
                return await self.async_step_pairing_code()
            errors["base"] = error

        return self.async_show_form(
            step_id="pair",
            errors=errors,
            data_schema=vol.Schema({}),
        )

    async def async_step_pairing_code(
        self, user_input: Mapping[str, Any] | None = None
    ) -> FlowResult:
        """Ask for the user pairing code after the default one was rejected."""

        errors: dict[str, str] = {}
        if user_input is not None:
            code = str(user_input[CONF_PAIRING_CODE]).strip()
            if not PAIRING_CODE_PATTERN.fullmatch(code):
                errors[CONF_PAIRING_CODE] = "invalid_pairing_code"
            elif (error := await self._async_try_pairing(int(code))) is None:
                return await self._async_create_votronic_entry()
            else:
                errors["base"] = error

        return self.async_show_form(
            step_id="pairing_code",
            errors=errors,
            data_schema=vol.Schema({vol.Required(CONF_PAIRING_CODE): str}),
        )

    async def _async_try_pairing(self, pairing_code: int) -> str | None:
        """Pair and check the device; return the error key, None on success."""

        assert self._discovered_device is not None
        try:
            await _validate_pairing(
                self.hass,
                self._discovered_device.address,
                pairing_code,
            )
        except CannotConnect:
            return "cannot_connect"
        except PairingNotAccepted:
            return "pairing_not_accepted"
        except WrongPasskey:
            return "wrong_pairing_code"
        except PairingFailed:
            return "local_adapter_required"
        except UnsupportedDevice:
            return "unsupported_device"
        return None

    async def _async_create_votronic_entry(self) -> FlowResult:
        assert self._discovered_device is not None
        address = _normalize_address(self._discovered_device.address)
        await self.async_set_unique_id(address)
        self._abort_if_unique_id_configured()
        name = _device_name(address)
        return self.async_create_entry(
            title=name,
            data={CONF_ADDRESS: address, CONF_NAME: name},
        )


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""


class PairingFailed(Exception):
    """Error to indicate pairing failed."""


class UnsupportedDevice(Exception):
    """Error to indicate this is not a supported Votronic device."""
