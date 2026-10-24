"""Pairing through BlueZ with a passkey agent, against a fake system bus."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from dbus_fast import MessageType, Variant
from dbus_fast.service import ServiceInterface
import pytest

from custom_components.votronic_ble import pairing
from custom_components.votronic_ble.pairing import (
    AGENT_PATH,
    PairingError,
    PairingNotAccepted,
    PairingUnavailable,
    WrongPasskey,
    async_pair,
    async_prefer_le,
    async_remove_pairings,
    async_reset_pairing,
    bluez_device_path,
)

ADDRESS = "AA:BB:CC:DD:EE:01"
DEVICE_PATH = "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_01"
OK = SimpleNamespace(message_type=MessageType.METHOD_RETURN, error_name=None, body=[])
# A reply that never comes, like from a hanging bluetoothd.
SILENT = object()


def _error(name: str) -> SimpleNamespace:
    return SimpleNamespace(message_type=MessageType.ERROR, error_name=name, body=["details"])


def _ble_device(path: str | None = DEVICE_PATH) -> MagicMock:
    device = MagicMock(name="BLEDevice")
    device.address = ADDRESS
    device.details = {"path": path, "props": {}} if path else {"source": "proxy"}
    return device


def _managed(*devices: tuple[str, str, bool]) -> SimpleNamespace:
    """Reply of GetManagedObjects with an adapter and devices (path, address, paired)."""

    objects: dict = {"/org/bluez/hci0": {"org.bluez.Adapter1": {}}}
    for path, address, paired in devices:
        objects[path] = {
            "org.bluez.Device1": {
                "Address": Variant("s", address),
                "Adapter": Variant("o", path.rsplit("/", 1)[0]),
                "Paired": Variant("b", paired),
            }
        }
    return SimpleNamespace(message_type=MessageType.METHOD_RETURN, error_name=None, body=[objects])


def _agent_methods(agent: ServiceInterface) -> dict:
    return {method.name: method for method in ServiceInterface._get_methods(agent)}


class FakeBus:
    """Records BlueZ calls; Pair lets the agent answer like BlueZ would.

    A reply is a message, SILENT, an exception to raise, or a list of these
    for consecutive calls, of which the last one repeats.
    """

    def __init__(self, replies: dict | None = None, ask_passkey: bool = False) -> None:
        self.replies = replies or {}
        self.ask_passkey = ask_passkey
        self.calls: list[tuple[str, str, list]] = []
        self.exported: dict[str, ServiceInterface] = {}
        self.entered: list[int] = []
        self.disconnected = False

    async def connect(self) -> FakeBus:
        return self

    def export(self, path: str, interface: ServiceInterface) -> None:
        self.exported[path] = interface

    async def call(self, message) -> SimpleNamespace:
        self.calls.append((message.path, message.member, list(message.body)))
        if message.member == "Pair" and self.ask_passkey:
            agent = self.exported[AGENT_PATH]
            self.entered.append(_agent_methods(agent)["RequestPasskey"].fn(agent, message.path))
        reply = self.replies.get(message.member, OK)
        if isinstance(reply, list):
            reply = reply.pop(0) if len(reply) > 1 else reply[0]
        if reply is SILENT:
            await asyncio.Event().wait()
        if isinstance(reply, Exception):
            raise reply
        return reply

    def disconnect(self) -> None:
        self.disconnected = True

    def members(self) -> list[str]:
        return [member for _, member, _ in self.calls]


def _use(bus: FakeBus):
    return patch.object(pairing, "MessageBus", lambda bus_type: bus)


def test_agent_methods_have_the_bluez_signatures() -> None:
    agent = pairing._PasskeyAgent(12345)
    methods = _agent_methods(agent)
    assert {name: (m.in_signature, m.out_signature) for name, m in methods.items()} == {
        "Cancel": ("", ""),
        "Release": ("", ""),
        "RequestPasskey": ("o", "u"),
        "RequestPinCode": ("o", "s"),
    }
    assert not agent.passkey_requested
    assert methods["RequestPinCode"].fn(agent, DEVICE_PATH) == "012345"
    assert agent.passkey_requested


def test_bluez_device_path() -> None:
    assert bluez_device_path(_ble_device()) == DEVICE_PATH
    assert bluez_device_path(_ble_device(None)) is None
    device = MagicMock()
    device.details = MagicMock()
    assert bluez_device_path(device) is None


async def test_pair_enters_the_passkey() -> None:
    bus = FakeBus(ask_passkey=True)
    with _use(bus):
        await async_pair(_ble_device(), 173928)
    assert bus.entered == [173928]
    assert bus.members() == ["RegisterAgent", "Pair", "UnregisterAgent"]
    assert bus.calls[0][2] == [AGENT_PATH, "KeyboardOnly"]
    assert bus.calls[1][0] == DEVICE_PATH
    assert bus.disconnected


async def test_pair_accepts_an_existing_bond() -> None:
    bus = FakeBus({"Pair": _error("org.bluez.Error.AlreadyExists")})
    with _use(bus):
        await async_pair(_ble_device(), 173928)


@pytest.mark.parametrize(
    ("ask_passkey", "error_name", "raised"),
    [
        # Asked for the passkey, then refused: the code was wrong.
        (True, "org.bluez.Error.AuthenticationFailed", WrongPasskey),
        # Refused without asking: the connector is not in pairing mode.
        (False, "org.bluez.Error.AuthenticationFailed", PairingNotAccepted),
        (False, "org.bluez.Error.AuthenticationCanceled", PairingNotAccepted),
        (False, "org.bluez.Error.ConnectionAttemptFailed", PairingError),
    ],
)
async def test_pair_failures(ask_passkey: bool, error_name: str, raised: type) -> None:
    bus = FakeBus({"Pair": _error(error_name)}, ask_passkey=ask_passkey)
    with _use(bus), pytest.raises(raised):
        await async_pair(_ble_device(), 173928)
    assert bus.members()[-1] == "UnregisterAgent"
    assert bus.disconnected


async def test_pair_without_agent_registration() -> None:
    bus = FakeBus({"RegisterAgent": _error("org.bluez.Error.AlreadyExists")})
    with _use(bus), pytest.raises(PairingError):
        await async_pair(_ble_device(), 173928)
    assert "Pair" not in bus.members()
    assert bus.disconnected


async def test_pair_cancels_after_the_timeout() -> None:
    bus = FakeBus({"Pair": SILENT})
    with _use(bus), patch.object(pairing, "PAIR_TIMEOUT_SECONDS", 0.01):
        with pytest.raises(PairingError):
            await async_pair(_ble_device(), 173928)
    assert bus.members() == ["RegisterAgent", "Pair", "CancelPairing", "UnregisterAgent"]


@pytest.mark.parametrize(
    ("replies", "message"),
    [
        ({"RegisterAgent": SILENT}, "No answer to RegisterAgent"),
        # The system bus connection breaks: cleaning up fails as well and
        # must not hide the error of Pair.
        (
            {"Pair": EOFError(), "CancelPairing": EOFError(), "UnregisterAgent": SILENT},
            "Pair failed",
        ),
    ],
)
async def test_pair_fails_when_bluez_does_not_answer(replies: dict, message: str) -> None:
    bus = FakeBus(replies)
    with (
        _use(bus),
        patch.object(pairing, "DBUS_TIMEOUT_SECONDS", 0.01),
        pytest.raises(PairingError, match=message),
    ):
        await async_pair(_ble_device(), 173928)
    assert bus.disconnected


async def test_pair_needs_a_local_adapter() -> None:
    with pytest.raises(PairingUnavailable):
        await async_pair(_ble_device(None), 173928)

    def no_bus(bus_type):
        raise FileNotFoundError("no system bus")

    with patch.object(pairing, "MessageBus", no_bus), pytest.raises(PairingUnavailable):
        await async_pair(_ble_device(), 173928)

    class SilentBus(FakeBus):
        async def connect(self) -> FakeBus:
            await asyncio.Event().wait()

    with (
        _use(SilentBus()),
        patch.object(pairing, "DBUS_TIMEOUT_SECONDS", 0.01),
        pytest.raises(PairingUnavailable),
    ):
        await async_pair(_ble_device(), 173928)


async def test_prefer_le_sets_the_bearer() -> None:
    bus = FakeBus()
    with _use(bus):
        await async_prefer_le(_ble_device())
    path, member, body = bus.calls[0]
    assert (path, member) == (DEVICE_PATH, "Set")
    assert body[:2] == ["org.bluez.Device1", "PreferredBearer"]
    assert body[2].value == "le"
    assert bus.disconnected


async def test_prefer_le_is_best_effort() -> None:
    # A BlueZ without PreferredBearer, a hanging bluetoothd, no system bus, a
    # device behind a proxy.
    with _use(FakeBus({"Set": _error("org.freedesktop.DBus.Error.InvalidArgs")})):
        await async_prefer_le(_ble_device())
    with _use(FakeBus({"Set": SILENT})), patch.object(pairing, "DBUS_TIMEOUT_SECONDS", 0.01):
        await async_prefer_le(_ble_device())

    def no_bus(bus_type):
        raise FileNotFoundError("no system bus")

    with patch.object(pairing, "MessageBus", no_bus):
        await async_prefer_le(_ble_device())
    await async_prefer_le(_ble_device(None))


async def test_remove_pairings_of_every_adapter() -> None:
    other_adapter = "/org/bluez/hci1/dev_AA_BB_CC_DD_EE_01"
    bus = FakeBus(
        {
            "GetManagedObjects": _managed(
                (DEVICE_PATH, ADDRESS, True),
                (other_adapter, ADDRESS, True),
                ("/org/bluez/hci2/dev_AA_BB_CC_DD_EE_01", ADDRESS, False),
                ("/org/bluez/hci0/dev_AA_BB_CC_DD_EE_02", "AA:BB:CC:DD:EE:02", True),
            )
        }
    )
    with _use(bus):
        assert await async_remove_pairings(ADDRESS.lower()) == [DEVICE_PATH, other_adapter]
    assert [(path, body) for path, member, body in bus.calls if member == "RemoveDevice"] == [
        ("/org/bluez/hci0", [DEVICE_PATH]),
        ("/org/bluez/hci1", [other_adapter]),
    ]
    assert bus.disconnected


async def test_remove_pairings_fails_when_bluez_refuses() -> None:
    bus = FakeBus(
        {
            "GetManagedObjects": _managed((DEVICE_PATH, ADDRESS, True)),
            "RemoveDevice": _error("org.bluez.Error.Failed"),
        }
    )
    with _use(bus), pytest.raises(PairingError):
        await async_remove_pairings(ADDRESS)


async def test_reset_waits_until_bluez_finds_the_device_again() -> None:
    unknown = _error("org.freedesktop.DBus.Error.UnknownObject")
    bus = FakeBus(
        {
            "GetManagedObjects": _managed((DEVICE_PATH, ADDRESS, True)),
            "Get": [unknown, unknown, OK],
        }
    )
    with _use(bus), patch.object(pairing, "REAPPEAR_POLL_SECONDS", 0):
        await async_reset_pairing(_ble_device())
    assert bus.members() == ["GetManagedObjects", "RemoveDevice", "Get", "Get", "Get"]


async def test_reset_without_an_earlier_pairing() -> None:
    bus = FakeBus({"GetManagedObjects": _managed((DEVICE_PATH, ADDRESS, False))})
    with _use(bus):
        await async_reset_pairing(_ble_device())
    assert bus.members() == ["GetManagedObjects"]


async def test_reset_fails_when_the_device_does_not_come_back() -> None:
    bus = FakeBus(
        {
            "GetManagedObjects": _managed((DEVICE_PATH, ADDRESS, True)),
            "Get": _error("org.freedesktop.DBus.Error.UnknownObject"),
        }
    )
    with (
        _use(bus),
        patch.object(pairing, "REAPPEAR_TIMEOUT_SECONDS", 0.05),
        patch.object(pairing, "REAPPEAR_POLL_SECONDS", 0.01),
        pytest.raises(PairingError, match="did not find"),
    ):
        await async_reset_pairing(_ble_device())


async def test_reset_is_skipped_without_bluez() -> None:
    # A device behind a proxy, no system bus.
    await async_reset_pairing(_ble_device(None))

    def no_bus(bus_type):
        raise FileNotFoundError("no system bus")

    with patch.object(pairing, "MessageBus", no_bus):
        await async_reset_pairing(_ble_device())
