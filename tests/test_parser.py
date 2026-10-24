"""Tests for the Votronic BLE parser."""

from __future__ import annotations

from importlib import util
from pathlib import Path
import sys
import unittest

_INTEGRATION = Path(__file__).resolve().parents[1] / "custom_components" / "votronic_ble"
_PARSER_PATH = _INTEGRATION / "parser.py"
_SPEC = util.spec_from_file_location("votronic_parser", _PARSER_PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
_PARSER = util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _PARSER
_SPEC.loader.exec_module(_PARSER)

VotronicFrameError = _PARSER.VotronicFrameError
FRAME_KEYS = _PARSER.FRAME_KEYS
FrameType = _PARSER.FrameType
battery_status_to_string = _PARSER.battery_status_to_string
frame_types_for_key = _PARSER.frame_types_for_key
parse_battery_computer = _PARSER.parse_battery_computer
parse_solar_charger = _PARSER.parse_solar_charger
solar_charger_status_to_string = _PARSER.solar_charger_status_to_string


class VotronicParserTest(unittest.TestCase):
    """Test known frames from syssi/esphome-votronic."""

    def test_battery_computer_frame(self) -> None:
        frame = bytes(
            [
                0xE8,
                0x04,
                0xBF,
                0x04,
                0x09,
                0x01,
                0x60,
                0x00,
                0x5F,
                0x00,
                0x9A,
                0xFE,
                0xFF,
                0xF0,
                0x0A,
                0x5E,
                0x14,
                0x54,
                0x02,
                0x04,
            ]
        )

        values = parse_battery_computer(frame).values

        self.assertAlmostEqual(values["battery_voltage"], 12.56)
        self.assertAlmostEqual(values["secondary_battery_voltage"], 12.15)
        self.assertEqual(values["battery_capacity_remaining"], 265)
        self.assertEqual(values["state_of_charge"], 95)
        self.assertAlmostEqual(values["current"], -0.358)
        self.assertFalse(values["charging"])
        self.assertTrue(values["discharging"])
        self.assertAlmostEqual(values["battery_nominal_capacity"], 280.0)

    def test_solar_charger_frame(self) -> None:
        frame = bytes(
            [
                0xE8,
                0x04,
                0x76,
                0x05,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x06,
                0x56,
                0x00,
                0x09,
                0x18,
                0x00,
                0x22,
                0x00,
                0x00,
                0x00,
            ]
        )

        values = parse_solar_charger(frame).values

        self.assertAlmostEqual(values["battery_voltage"], 12.56)
        self.assertAlmostEqual(values["pv_voltage"], 13.98)
        self.assertAlmostEqual(values["pv_current"], 0.0)
        self.assertEqual(values["pv_controller_temperature"], 6.0)
        self.assertEqual(values["battery_status"], "Standby")
        self.assertEqual(values["pv_controller_status"], "Active")
        self.assertTrue(values["controller_active"])
        self.assertFalse(values["current_reduction"])
        self.assertFalse(values["aes_active"])
        self.assertEqual(values["charged_capacity"], 24)
        self.assertEqual(values["charged_energy"], 340)
        self.assertEqual(values["pv_power"], 0)

    def test_frame_keys_match_parser_output(self) -> None:
        battery = parse_battery_computer(bytes(20))
        solar = parse_solar_charger(bytes(19))
        self.assertEqual(set(battery.values), set(FRAME_KEYS[FrameType.BATTERY_COMPUTER]))
        self.assertEqual(set(solar.values), set(FRAME_KEYS[FrameType.SOLAR_CHARGER]))

    def test_frame_types_for_key(self) -> None:
        self.assertEqual(
            frame_types_for_key("battery_voltage"),
            {FrameType.BATTERY_COMPUTER, FrameType.SOLAR_CHARGER},
        )
        self.assertEqual(frame_types_for_key("state_of_charge"), {FrameType.BATTERY_COMPUTER})
        self.assertEqual(frame_types_for_key("pv_power"), {FrameType.SOLAR_CHARGER})
        self.assertEqual(frame_types_for_key("does_not_exist"), frozenset())

    def test_invalid_frame_length(self) -> None:
        for parse, length in (
            (parse_battery_computer, 1),
            (parse_battery_computer, 19),
            (parse_battery_computer, 21),
            (parse_solar_charger, 18),
            (parse_solar_charger, 20),
        ):
            with self.subTest(parse=parse.__name__, length=length):
                with self.assertRaises(VotronicFrameError):
                    parse(bytes(length))

    def test_battery_status_texts(self) -> None:
        # The highest phase bit wins, as in syssi/esphome-votronic.
        for mask, text in (
            (0x00, "Standby"),
            (0x01, "I phase"),
            (0x02, "U1 phase"),
            (0x03, "U1 phase"),
            (0x04, "U2 phase"),
            (0x07, "U2 phase"),
            (0x08, "U3 phase"),
            (0x0F, "U3 phase"),
            (0x10, "Unknown (0x10)"),
            (0xF0, "Unknown (0xF0)"),
        ):
            with self.subTest(mask=mask):
                self.assertEqual(battery_status_to_string(mask), text)

    def test_solar_charger_status_texts(self) -> None:
        # The highest state bit wins, as in syssi/esphome-votronic.
        for mask, text in (
            (0x00, "Standby"),
            (0x08, "Active"),
            (0x10, "Reduced"),
            (0x18, "Reduced"),
            (0x20, "AES active"),
            (0x38, "AES active"),
            (0x01, "Unknown (0x01)"),
            (0xC7, "Unknown (0xC7)"),
        ):
            with self.subTest(mask=mask):
                self.assertEqual(solar_charger_status_to_string(mask), text)

    def test_solar_charger_frame_status_bytes(self) -> None:
        frame = bytearray(19)
        frame[8] = 0x04
        frame[9] = 25
        values = parse_solar_charger(frame).values
        self.assertEqual(values["battery_status"], "U2 phase")
        self.assertEqual(values["pv_controller_status"], "Standby")
        # Without a controller state the temperature byte is not valid.
        self.assertIsNone(values["pv_controller_temperature"])

        frame[12] = 0x30
        values = parse_solar_charger(frame).values
        self.assertEqual(values["pv_controller_status"], "AES active")
        self.assertEqual(values["pv_controller_temperature"], 25.0)
        self.assertFalse(values["controller_active"])
        self.assertTrue(values["current_reduction"])
        self.assertTrue(values["aes_active"])


if __name__ == "__main__":
    unittest.main()
