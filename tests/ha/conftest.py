"""Fixtures for the Home Assistant tests, see docs/development.md."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest

BLUETOOTH = "custom_components.votronic_ble.bluetooth"


@pytest.fixture
def ble_device() -> Iterator[MagicMock]:
    """Make the device visible; without this fixture it is never in range."""

    device = MagicMock(name="BLEDevice")
    with patch(f"{BLUETOOTH}.bluetooth.async_ble_device_from_address", return_value=device):
        yield device


@pytest.fixture(autouse=True)
def no_ble_device() -> Iterator[None]:
    """Keep every Votronic device out of range unless a test uses ble_device."""

    with patch(f"{BLUETOOTH}.bluetooth.async_ble_device_from_address", return_value=None):
        yield
