"""Base entity for the Votronic integration."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity, EntityDescription
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .bluetooth import VotronicBluetoothDevice
from .const import ATTRIBUTION, DOMAIN
from .parser import frame_types_for_key


def device_info(device: VotronicBluetoothDevice) -> DeviceInfo:
    """Return the device registry entry for a Bluetooth Connector."""

    address = device.address.upper()
    return DeviceInfo(
        identifiers={(DOMAIN, address)},
        name=device.name,
        manufacturer="Votronic",
        model="Bluetooth Connector S-BC",
        connections={("bluetooth", address)},
    )


def async_add_entities_per_frame(
    device: VotronicBluetoothDevice,
    descriptions: Iterable[EntityDescription],
    factory: Callable[[VotronicBluetoothDevice, Any], Entity],
    async_add_entities: AddEntitiesCallback,
) -> Callable[[], None]:
    """Create entities as soon as a frame of their type has been received.

    Returns the unsubscribe callback for the device listener.
    """

    pending = list(descriptions)

    @callback
    def _add_ready() -> None:
        ready = [d for d in pending if frame_types_for_key(d.key) & device.seen_frame_types]
        if not ready:
            return
        for d in ready:
            pending.remove(d)
        async_add_entities(factory(device, d) for d in ready)

    _add_ready()
    return device.async_subscribe(_add_ready)


class VotronicEntity(Entity):
    """Base class for Votronic entities."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True

    def __init__(self, device: VotronicBluetoothDevice, key: str) -> None:
        """Initialize the entity."""

        self._device = device
        self._key = key
        address = device.address.upper()
        self._attr_unique_id = f"{address}_{key}"
        self._attr_device_info = device_info(device)

    @property
    def available(self) -> bool:
        """Return if the entity is available."""

        # A current frame without the value, e.g. the controller temperature
        # in standby, makes the state unknown, not unavailable.
        return self._device.connected and self._device.is_current(self._key)

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""

        self.async_on_remove(self._device.async_subscribe(self.async_write_ha_state))
