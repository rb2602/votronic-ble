"""Helpers shared by the Home Assistant tests.

tests/ha is not a package, so that the unittest run in CI does not collect
these tests; pytest puts this folder on sys.path, and the tests import this
module as helpers.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.votronic_ble.const import (
    CHAR_BATTERY_COMPUTER_UUID,
    CHAR_SOLAR_CHARGER_UUID,
    DOMAIN,
)

ALL_CHARACTERISTICS = (CHAR_BATTERY_COMPUTER_UUID, CHAR_SOLAR_CHARGER_UUID)


def make_client(characteristics: tuple[str, ...] = ALL_CHARACTERISTICS) -> MagicMock:
    """Return a connected fake Bleak client offering the given characteristics."""

    client = MagicMock(name="BleakClient")
    client.is_connected = True
    client.services.get_characteristic.side_effect = lambda uuid: (
        object() if uuid in characteristics else None
    )
    client.start_notify = AsyncMock()
    client.stop_notify = AsyncMock()
    client.disconnect = AsyncMock()
    client.pair = AsyncMock()
    return client


def make_entry(number: int = 1) -> MockConfigEntry:
    """Return a config entry for the Votronic device AA:BB:CC:DD:EE:0<number>."""

    address = f"AA:BB:CC:DD:EE:0{number}"
    return MockConfigEntry(
        domain=DOMAIN,
        title=f"Votronic S-BC EE0{number}",
        unique_id=address,
        data={"address": address, "name": f"Votronic S-BC EE0{number}"},
    )
