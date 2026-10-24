"""Fixtures for the Home Assistant tests, see docs/development.md."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import custom_components

pytest_plugins = "pytest_homeassistant_custom_component"

# The plugin ships its own custom_components package for its test
# integrations; add this repository's folder so Home Assistant finds votronic_ble.
_CUSTOM_COMPONENTS = str(Path(__file__).resolve().parents[2] / "custom_components")
if _CUSTOM_COMPONENTS not in custom_components.__path__:
    custom_components.__path__.append(_CUSTOM_COMPONENTS)

BLUETOOTH = "custom_components.votronic_ble.bluetooth"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let Home Assistant load integrations from custom_components."""


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
