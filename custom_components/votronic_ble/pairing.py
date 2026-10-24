"""Pairing with the Votronic Bluetooth Connector through BlueZ.

The Bluetooth Connector bonds only while it is in pairing mode and asks for a
six-digit passkey. bleak's pair() registers no BlueZ agent that could enter
it, so pairing exports an agent on its own D-Bus connection and calls Pair()
through that connection: BlueZ asks the agent of the caller. dbus-fast comes
with the Bluetooth integration of Home Assistant.

The connector advertises a public address without the "BR/EDR not supported"
flag. BlueZ therefore treats a device it has not used before as dual mode and
connects over BR/EDR, which fails; PreferredBearer le avoids that.

An earlier pairing is removed before pairing: it may be stale, because the
connector forgets its pairings when its Key button is held, and for a device
paired over LE, Pair() would try BR/EDR and fail with a page timeout.
Removing the config entry removes the pairing as well.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
import logging
from typing import Any

from bleak.backends.device import BLEDevice
from dbus_fast import BusType, Message, MessageType, Variant
from dbus_fast.aio import MessageBus
from dbus_fast.annotations import DBusObjectPath, DBusStr, DBusUInt32
from dbus_fast.errors import AuthError, DBusError
from dbus_fast.service import ServiceInterface, method

_LOGGER = logging.getLogger(__name__)

BLUEZ_SERVICE = "org.bluez"
AGENT_MANAGER_PATH = "/org/bluez"
AGENT_PATH = "/org/homeassistant/votronic/pairing_agent"
# Every D-Bus call has a timeout, so a hanging bluetoothd cannot block setup.
DBUS_TIMEOUT_SECONDS = 10
PAIR_TIMEOUT_SECONDS = 30
# How long BlueZ may take to see the connector again after its pairing was
# removed; the connector advertises while it is in pairing mode.
REAPPEAR_TIMEOUT_SECONDS = 30
REAPPEAR_POLL_SECONDS = 0.5

# Errors of Device1.Pair when the connector refused the bonding.
AUTHENTICATION_ERRORS = frozenset(
    {
        "org.bluez.Error.AuthenticationCanceled",
        "org.bluez.Error.AuthenticationFailed",
        "org.bluez.Error.AuthenticationRejected",
        "org.bluez.Error.AuthenticationTimeout",
    }
)


class PairingUnavailable(Exception):
    """The device is not reached through a Bluetooth adapter of this host."""


class PairingNotAccepted(Exception):
    """The connector refused without asking for the passkey: not in pairing mode."""


class WrongPasskey(Exception):
    """The connector asked for the passkey and rejected it."""


class PairingError(Exception):
    """Pairing failed for another reason, for example a lost connection."""


class _PasskeyAgent(ServiceInterface):
    """BlueZ agent that enters the passkey and records whether it was asked for."""

    def __init__(self, passkey: int) -> None:
        super().__init__("org.bluez.Agent1")
        self._passkey = passkey
        self.passkey_requested = False

    @method()
    def Release(self):
        """BlueZ no longer uses the agent."""

    @method()
    def RequestPasskey(self, device: DBusObjectPath) -> DBusUInt32:
        """Enter the passkey."""

        self.passkey_requested = True
        return self._passkey

    @method()
    def RequestPinCode(self, device: DBusObjectPath) -> DBusStr:
        """Enter the passkey as a PIN code for legacy pairing."""

        self.passkey_requested = True
        return f"{self._passkey:06d}"

    @method()
    def Cancel(self):
        """BlueZ cancelled the request."""


def bluez_device_path(ble_device: BLEDevice) -> str | None:
    """Return the BlueZ object path, None for a device behind a Bluetooth proxy."""

    details = ble_device.details
    path = details.get("path") if isinstance(details, dict) else None
    return path if isinstance(path, str) and path.startswith("/org/bluez/") else None


@asynccontextmanager
async def _system_bus() -> AsyncIterator[MessageBus]:
    try:
        async with asyncio.timeout(DBUS_TIMEOUT_SECONDS):
            bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    except TimeoutError as err:
        raise PairingUnavailable("The system D-Bus did not answer") from err
    except (OSError, ValueError, AuthError) as err:
        raise PairingUnavailable(f"No access to the system D-Bus: {err}") from err
    try:
        yield bus
    finally:
        bus.disconnect()


async def _call(
    bus: MessageBus,
    path: str,
    interface: str,
    member: str,
    signature: str = "",
    body: list[Any] | None = None,
    timeout: float | None = None,
) -> Message:
    """Call BlueZ; no answer or a lost connection raises PairingError.

    BlueZ errors come back as a reply of type ERROR.
    """

    timeout = DBUS_TIMEOUT_SECONDS if timeout is None else timeout
    message = Message(
        destination=BLUEZ_SERVICE,
        path=path,
        interface=interface,
        member=member,
        signature=signature,
        body=body or [],
    )
    try:
        async with asyncio.timeout(timeout):
            return await bus.call(message)
    except TimeoutError as err:
        raise PairingError(f"No answer to {member} within {timeout} seconds") from err
    # dbus-fast 4, which Home Assistant 2026.5 ships, has no common base class
    # for its errors.
    except (EOFError, OSError, ValueError, DBusError) as err:
        raise PairingError(f"{member} failed: {err!r}") from err


def _value(properties: dict[str, Variant], name: str) -> Any:
    variant = properties.get(name)
    return None if variant is None else variant.value


async def _paired_devices(bus: MessageBus, address: str) -> list[tuple[str, str]]:
    """Return adapter and device path of every pairing of this host with address."""

    reply = await _call(bus, "/", "org.freedesktop.DBus.ObjectManager", "GetManagedObjects")
    if reply.message_type == MessageType.ERROR:
        raise PairingError(f"Could not list the BlueZ devices: {reply.error_name}")
    return [
        (_value(device, "Adapter"), path)
        for path, interfaces in reply.body[0].items()
        if (device := interfaces.get("org.bluez.Device1")) is not None
        and str(_value(device, "Address")).upper() == address.upper()
        and _value(device, "Paired")
    ]


async def _is_known(bus: MessageBus, path: str) -> bool:
    reply = await _call(
        bus,
        path,
        "org.freedesktop.DBus.Properties",
        "Get",
        "ss",
        ["org.bluez.Device1", "Address"],
    )
    return reply.message_type != MessageType.ERROR


async def async_remove_pairings(address: str) -> list[str]:
    """Remove every pairing of a Bluetooth adapter of this host with address.

    Returns the BlueZ paths of the removed devices. Raises PairingUnavailable
    without access to the system D-Bus and PairingError when BlueZ fails.
    """

    async with _system_bus() as bus:
        paired = await _paired_devices(bus, address)
        for adapter, device in paired:
            reply = await _call(bus, adapter, "org.bluez.Adapter1", "RemoveDevice", "o", [device])
            if reply.message_type == MessageType.ERROR:
                raise PairingError(f"Could not remove the pairing {device}: {reply.error_name}")
            _LOGGER.debug("Removed the pairing %s", device)
    return [device for _, device in paired]


async def async_reset_pairing(ble_device: BLEDevice) -> None:
    """Remove an earlier pairing before pairing again, see the module docstring.

    BlueZ forgets the device together with its pairing and finds it again
    with its next advertisement; this waits for that, so that the connection
    and Pair() that follow find it. Does nothing for a device behind a
    Bluetooth proxy or without access to the system D-Bus. Raises PairingError
    when BlueZ fails or does not find the device again.
    """

    path = bluez_device_path(ble_device)
    if path is None:
        return
    try:
        removed = await async_remove_pairings(ble_device.address)
    except PairingUnavailable as err:
        _LOGGER.debug("Could not look for an earlier pairing of %s: %s", path, err)
        return
    if path not in removed:
        return
    async with _system_bus() as bus:
        try:
            async with asyncio.timeout(REAPPEAR_TIMEOUT_SECONDS):
                while not await _is_known(bus, path):
                    await asyncio.sleep(REAPPEAR_POLL_SECONDS)
        except TimeoutError as err:
            raise PairingError(
                f"BlueZ did not find {path} again within {REAPPEAR_TIMEOUT_SECONDS} seconds"
            ) from err


async def async_prefer_le(ble_device: BLEDevice) -> None:
    """Make BlueZ connect the device over LE, see the module docstring.

    Does nothing for a device behind a Bluetooth proxy or when BlueZ has no
    PreferredBearer property.
    """

    path = bluez_device_path(ble_device)
    if path is None:
        return
    try:
        async with _system_bus() as bus:
            reply = await _call(
                bus,
                path,
                "org.freedesktop.DBus.Properties",
                "Set",
                "ssv",
                ["org.bluez.Device1", "PreferredBearer", Variant("s", "le")],
            )
    except (PairingUnavailable, PairingError) as err:
        _LOGGER.debug("Could not prefer LE for %s: %s", path, err)
        return
    if reply.message_type == MessageType.ERROR:
        _LOGGER.debug("Could not prefer LE for %s: %s %s", path, reply.error_name, reply.body)


async def async_pair(ble_device: BLEDevice, passkey: int) -> None:
    """Pair through BlueZ and enter the passkey when the connector asks for it.

    Expects no earlier pairing, see async_reset_pairing.

    Raises PairingUnavailable for a device behind a Bluetooth proxy,
    PairingNotAccepted when the connector refuses without asking for the
    passkey, WrongPasskey when it rejects the passkey, and PairingError
    otherwise.
    """

    path = bluez_device_path(ble_device)
    if path is None:
        raise PairingUnavailable("The device is not reached through a local adapter")
    agent = _PasskeyAgent(passkey)
    async with _system_bus() as bus:
        bus.export(AGENT_PATH, agent)
        reply = await _call(
            bus,
            AGENT_MANAGER_PATH,
            "org.bluez.AgentManager1",
            "RegisterAgent",
            "os",
            [AGENT_PATH, "KeyboardOnly"],
        )
        if reply.message_type == MessageType.ERROR:
            raise PairingError(f"Could not register the pairing agent: {reply.error_name}")
        try:
            reply = await _call(
                bus, path, "org.bluez.Device1", "Pair", timeout=PAIR_TIMEOUT_SECONDS
            )
        except PairingError:
            # Best effort: the original error is the one to report.
            with suppress(PairingError):
                await _call(bus, path, "org.bluez.Device1", "CancelPairing")
            raise
        finally:
            with suppress(PairingError):
                await _call(
                    bus,
                    AGENT_MANAGER_PATH,
                    "org.bluez.AgentManager1",
                    "UnregisterAgent",
                    "o",
                    [AGENT_PATH],
                )

    if (
        reply.message_type != MessageType.ERROR
        or reply.error_name == "org.bluez.Error.AlreadyExists"
    ):
        return
    _LOGGER.debug(
        "Pairing %s failed: %s %s, passkey requested: %s",
        path,
        reply.error_name,
        reply.body,
        agent.passkey_requested,
    )
    if reply.error_name in AUTHENTICATION_ERRORS:
        raise WrongPasskey if agent.passkey_requested else PairingNotAccepted
    raise PairingError(f"{reply.error_name}: {reply.body}")
