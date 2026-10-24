"""Parser for Votronic Bluetooth monitoring notifications."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class FrameType(StrEnum):
    """Votronic BLE frame source."""

    BATTERY_COMPUTER = "battery_computer"
    SOLAR_CHARGER = "solar_charger"


@dataclass(frozen=True)
class ParsedFrame:
    """Decoded values from one Votronic BLE frame."""

    frame_type: FrameType
    values: dict[str, Any]


class VotronicFrameError(ValueError):
    """Raised when a Votronic frame cannot be decoded."""


# Which value keys each frame type delivers. Entities are created only once a
# frame of a matching type has been received, so a Bluetooth Connector without
# a battery computer does not get battery entities.
FRAME_KEYS: dict[FrameType, frozenset[str]] = {
    FrameType.BATTERY_COMPUTER: frozenset(
        {
            "battery_voltage",
            "secondary_battery_voltage",
            "battery_capacity_remaining",
            "state_of_charge",
            "current",
            "power",
            "charging",
            "discharging",
            "battery_nominal_capacity",
        }
    ),
    FrameType.SOLAR_CHARGER: frozenset(
        {
            "battery_voltage",
            "pv_voltage",
            "pv_current",
            "pv_controller_temperature",
            "battery_status_bitmask",
            "battery_status",
            "pv_controller_status_bitmask",
            "pv_controller_status",
            "controller_active",
            "current_reduction",
            "aes_active",
            "charged_capacity",
            "charged_energy",
            "pv_power",
        }
    ),
}


def frame_types_for_key(key: str) -> frozenset[FrameType]:
    """Return the frame types that deliver a value key."""

    return frozenset(ft for ft, keys in FRAME_KEYS.items() if key in keys)


def _u16(data: bytes, index: int) -> int:
    return data[index] | (data[index + 1] << 8)


def _s24(data: bytes, index: int) -> int:
    value = data[index] | (data[index + 1] << 8) | (data[index + 2] << 16)
    if value & 0x800000:
        value |= ~0xFFFFFF
    return value


def parse_battery_computer(data: bytes | bytearray) -> ParsedFrame:
    """Decode a 20-byte battery computer notification."""

    payload = bytes(data)
    if len(payload) != 20:
        raise VotronicFrameError(f"Battery computer frame must be 20 bytes, got {len(payload)}")

    battery_voltage = _u16(payload, 0) * 0.01
    current = _s24(payload, 10) * 0.001

    return ParsedFrame(
        FrameType.BATTERY_COMPUTER,
        {
            "battery_voltage": battery_voltage,
            "secondary_battery_voltage": _u16(payload, 2) * 0.01,
            "battery_capacity_remaining": float(_u16(payload, 4)),
            "state_of_charge": float(payload[8]),
            "current": current,
            "power": current * battery_voltage,
            "charging": current > 0.0,
            "discharging": current < 0.0,
            "battery_nominal_capacity": _u16(payload, 13) * 0.1,
        },
    )


def parse_solar_charger(data: bytes | bytearray) -> ParsedFrame:
    """Decode a 19-byte solar charger notification."""

    payload = bytes(data)
    if len(payload) != 19:
        raise VotronicFrameError(f"Solar charger frame must be 19 bytes, got {len(payload)}")

    battery_status = payload[8]
    controller_status = payload[12]

    return ParsedFrame(
        FrameType.SOLAR_CHARGER,
        {
            "battery_voltage": _u16(payload, 0) * 0.01,
            "pv_voltage": _u16(payload, 2) * 0.01,
            "pv_current": _u16(payload, 4) * 0.1,
            "pv_controller_temperature": float(payload[9]) if controller_status != 0 else None,
            "battery_status_bitmask": float(battery_status),
            "battery_status": battery_status_to_string(battery_status),
            "pv_controller_status_bitmask": float(controller_status),
            "pv_controller_status": solar_charger_status_to_string(controller_status),
            "controller_active": bool(controller_status & (1 << 3)),
            "current_reduction": bool(controller_status & (1 << 4)),
            "aes_active": bool(controller_status & (1 << 5)),
            "charged_capacity": float(_u16(payload, 13)),
            "charged_energy": _u16(payload, 15) * 10.0,
            "pv_power": _u16(payload, 17) * 0.1,
        },
    )


def battery_status_to_string(mask: int) -> str:
    """Return the human-readable battery charging phase."""

    if mask == 0x00:
        return "Standby"
    if mask & (1 << 3):
        return "U3 phase"
    if mask & (1 << 2):
        return "U2 phase"
    if mask & (1 << 1):
        return "U1 phase"
    if mask & (1 << 0):
        return "I phase"
    return f"Unknown (0x{mask:02X})"


def solar_charger_status_to_string(mask: int) -> str:
    """Return the human-readable solar charger state."""

    if mask == 0x00:
        return "Standby"
    if mask & (1 << 5):
        return "AES active"
    if mask & (1 << 4):
        return "Reduced"
    if mask & (1 << 3):
        return "Active"
    return f"Unknown (0x{mask:02X})"
