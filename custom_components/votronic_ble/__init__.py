"""The Votronic integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, CONF_NAME, Platform
from homeassistant.core import HomeAssistant

from .bluetooth import VotronicBluetoothDevice
from .const import DOMAIN
from .pairing import PairingError, PairingUnavailable, async_remove_pairings

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

VotronicConfigEntry = ConfigEntry


async def async_setup_entry(hass: HomeAssistant, entry: VotronicConfigEntry) -> bool:
    """Set up Votronic from a config entry."""

    device = VotronicBluetoothDevice(
        hass,
        entry.data[CONF_ADDRESS],
        entry.data[CONF_NAME],
    )
    entry.runtime_data = device
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # The first connection can take long, e.g. while a phone is connected to
    # the connector, and must not hold up the start of Home Assistant. Home
    # Assistant cancels the task when the entry is unloaded.
    entry.async_create_background_task(
        hass, device.async_start(), f"{DOMAIN} connect {device.address}"
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: VotronicConfigEntry) -> bool:
    """Unload a config entry."""

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_stop()
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: VotronicConfigEntry) -> None:
    """Remove the pairing of this host with the connector, see pairing.py.

    Best effort: a failure is logged and the entry is removed anyway.
    """

    address = entry.data[CONF_ADDRESS]
    try:
        await async_remove_pairings(address)
    except PairingUnavailable as err:
        _LOGGER.debug("Could not remove the pairing with %s: %s", address, err)
    except PairingError as err:
        _LOGGER.warning("Could not remove the pairing with %s: %s", address, err)
