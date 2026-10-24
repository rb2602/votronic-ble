"""Config flow: discovery, manual setup and pairing."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from bleak import BleakError
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.config_entries import SOURCE_BLUETOOTH, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest

from custom_components.votronic_ble.config_flow import (
    CannotConnect,
    PairingFailed,
    UnsupportedDevice,
    _validate_pairing,
)
from custom_components.votronic_ble.const import (
    DEFAULT_PAIRING_CODE,
    DOMAIN,
    SERVICE_MONITORING_UUID,
)
from custom_components.votronic_ble.pairing import (
    PairingError,
    PairingNotAccepted,
    WrongPasskey,
)

from helpers import make_client, make_entry

FLOW = "custom_components.votronic_ble.config_flow"
ADDRESS = "AA:BB:CC:DD:EE:01"


def _service_info(name: str = "votronic 1", service_uuids: list[str] | None = None):
    return BluetoothServiceInfoBleak(
        name=name,
        address=ADDRESS.lower(),
        rssi=-60,
        manufacturer_data={},
        service_data={},
        service_uuids=service_uuids or [],
        source="local",
        device=MagicMock(),
        advertisement=None,
        connectable=True,
        time=0.0,
        tx_power=None,
    )


async def _discover(hass: HomeAssistant, info=None):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=info or _service_info()
    )


async def test_discovery_creates_entry_after_pairing(hass: HomeAssistant) -> None:
    result = await _discover(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "pair"
    flow = hass.config_entries.flow.async_get(result["flow_id"])
    assert flow["context"]["title_placeholders"] == {"name": "Votronic S-BC EE01"}

    with patch(f"{FLOW}._validate_pairing", AsyncMock()) as validate:
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Votronic S-BC EE01"
    assert result["data"] == {
        "address": ADDRESS,
        "name": "Votronic S-BC EE01",
    }
    assert result["result"].unique_id == ADDRESS
    validate.assert_awaited_once_with(hass, ADDRESS.lower(), DEFAULT_PAIRING_CODE)


async def test_discovery_by_service_uuid(hass: HomeAssistant) -> None:
    result = await _discover(hass, _service_info("S-BC", [SERVICE_MONITORING_UUID.upper()]))
    assert result["step_id"] == "pair"


async def test_discovery_of_other_device_aborts(hass: HomeAssistant) -> None:
    result = await _discover(hass, _service_info("Other sensor"))
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_supported"


async def test_discovery_of_configured_device_aborts(hass: HomeAssistant) -> None:
    make_entry(1).add_to_hass(hass)
    result = await _discover(hass)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (CannotConnect, "cannot_connect"),
        (PairingFailed, "local_adapter_required"),
        (PairingNotAccepted, "pairing_not_accepted"),
        (UnsupportedDevice, "unsupported_device"),
    ],
)
async def test_pairing_errors_keep_the_form(hass: HomeAssistant, error, reason) -> None:
    result = await _discover(hass)
    with patch(f"{FLOW}._validate_pairing", AsyncMock(side_effect=error)):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": reason}

    # The user can retry once the cause is fixed.
    with patch(f"{FLOW}._validate_pairing", AsyncMock()):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_rejected_default_code_asks_for_the_user_code(hass: HomeAssistant) -> None:
    result = await _discover(hass)
    with patch(f"{FLOW}._validate_pairing", AsyncMock(side_effect=WrongPasskey)):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "pairing_code"
    assert result["errors"] == {}

    with patch(f"{FLOW}._validate_pairing", AsyncMock()) as validate:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"pairing_code": " 012345 "}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    validate.assert_awaited_once_with(hass, ADDRESS.lower(), 12345)


@pytest.mark.parametrize(
    ("error", "errors"),
    [
        (WrongPasskey, {"base": "wrong_pairing_code"}),
        (PairingNotAccepted, {"base": "pairing_not_accepted"}),
        (CannotConnect, {"base": "cannot_connect"}),
    ],
)
async def test_user_code_errors_keep_the_form(hass: HomeAssistant, error, errors) -> None:
    result = await _discover(hass)
    with patch(f"{FLOW}._validate_pairing", AsyncMock(side_effect=WrongPasskey)):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    with patch(f"{FLOW}._validate_pairing", AsyncMock(side_effect=error)):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"pairing_code": "654321"}
        )
    assert result["step_id"] == "pairing_code"
    assert result["errors"] == errors


async def test_user_code_needs_six_digits(hass: HomeAssistant) -> None:
    result = await _discover(hass)
    with patch(f"{FLOW}._validate_pairing", AsyncMock(side_effect=WrongPasskey)):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    with patch(f"{FLOW}._validate_pairing", AsyncMock()) as validate:
        for code in ("12345", "1234567", "12a456"):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {"pairing_code": code}
            )
            assert result["errors"] == {"pairing_code": "invalid_pairing_code"}
    validate.assert_not_awaited()


async def test_user_flow_lists_discovered_devices(hass: HomeAssistant) -> None:
    infos = [_service_info(), _service_info("Other sensor")]
    infos[1].address = "11:22:33:44:55:66"
    with patch(f"{FLOW}.bluetooth.async_discovered_service_info", return_value=infos):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "user"
        choices = result["data_schema"].schema["address"].container
        assert choices == {ADDRESS: f"Votronic S-BC EE01 ({ADDRESS})"}

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"address": ADDRESS}
        )
    assert result["step_id"] == "pair"


async def test_user_flow_without_devices(hass: HomeAssistant) -> None:
    with patch(f"{FLOW}.bluetooth.async_discovered_service_info", return_value=[]):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "no_devices_found"}


async def test_validate_pairing_enters_the_code_through_bluez(
    hass: HomeAssistant, ble_device
) -> None:
    ble_device.details = {"path": "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_01"}
    client = make_client()
    steps = AsyncMock()
    steps.connect.return_value = client
    with (
        patch(f"{FLOW}.async_reset_pairing", steps.reset),
        patch(f"{FLOW}.async_prefer_le", steps.prefer_le),
        patch(f"{FLOW}.establish_connection", steps.connect),
        patch(f"{FLOW}.async_pair", steps.pair),
    ):
        await _validate_pairing(hass, ADDRESS, pairing_code=12345)
    # The earlier pairing goes first: removing it makes BlueZ forget the
    # preferred bearer and drops a connection.
    assert [name for name, _, _ in steps.mock_calls] == ["reset", "prefer_le", "connect", "pair"]
    steps.reset.assert_awaited_once_with(ble_device)
    steps.prefer_le.assert_awaited_once_with(ble_device)
    steps.pair.assert_awaited_once_with(ble_device, 12345)
    client.pair.assert_not_awaited()
    client.disconnect.assert_awaited_once()


async def test_validate_pairing_when_the_earlier_pairing_stays(
    hass: HomeAssistant, ble_device
) -> None:
    with (
        patch(f"{FLOW}.async_reset_pairing", AsyncMock(side_effect=PairingError("refused"))),
        patch(f"{FLOW}.establish_connection", AsyncMock()) as connect,
        pytest.raises(CannotConnect),
    ):
        await _validate_pairing(hass, ADDRESS)
    connect.assert_not_awaited()


@pytest.mark.parametrize(
    ("error", "raised"),
    [
        (WrongPasskey, WrongPasskey),
        (PairingNotAccepted, PairingNotAccepted),
        (PairingError("lost"), CannotConnect),
    ],
)
async def test_validate_pairing_bluez_failures(
    hass: HomeAssistant, ble_device, error, raised
) -> None:
    client = make_client()
    with (
        patch(f"{FLOW}.establish_connection", AsyncMock(return_value=client)),
        patch(f"{FLOW}.async_pair", AsyncMock(side_effect=error)),
        pytest.raises(raised),
    ):
        await _validate_pairing(hass, ADDRESS)
    client.disconnect.assert_awaited_once()


async def test_validate_pairing_behind_a_proxy_pairs_through_the_backend(
    hass: HomeAssistant, ble_device
) -> None:
    # The ble_device fixture has no BlueZ path, like a device behind a proxy.
    client = make_client()
    with patch(f"{FLOW}.establish_connection", AsyncMock(return_value=client)):
        await _validate_pairing(hass, ADDRESS)
    client.pair.assert_awaited_once()
    client.disconnect.assert_awaited_once()


async def test_validate_pairing_fails_for_backend_without_pairing(
    hass: HomeAssistant, ble_device
) -> None:
    client = make_client()
    client.pair.side_effect = NotImplementedError
    with (
        patch(f"{FLOW}.establish_connection", AsyncMock(return_value=client)),
        pytest.raises(PairingFailed),
    ):
        await _validate_pairing(hass, ADDRESS)
    client.disconnect.assert_awaited_once()


async def test_validate_pairing_failures(hass: HomeAssistant, ble_device) -> None:
    failing_pair = make_client()
    failing_pair.pair.side_effect = BleakError("rejected")
    without_characteristics = make_client(())
    cases = [
        (AsyncMock(side_effect=BleakError("unreachable")), CannotConnect),
        (AsyncMock(side_effect=TimeoutError), CannotConnect),
        (AsyncMock(return_value=failing_pair), PairingFailed),
        (AsyncMock(return_value=without_characteristics), UnsupportedDevice),
    ]
    for connect, error in cases:
        with patch(f"{FLOW}.establish_connection", connect), pytest.raises(error):
            await _validate_pairing(hass, ADDRESS)
    failing_pair.disconnect.assert_awaited_once()
    without_characteristics.disconnect.assert_awaited_once()


async def test_validate_pairing_without_device_in_range(hass: HomeAssistant) -> None:
    with pytest.raises(CannotConnect):
        await _validate_pairing(hass, ADDRESS)
