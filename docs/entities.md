# Entities

Entities appear with the first data of their device and stay after a
restart. The device is named after the last four digits of its address, for
example `Votronic S-BC EEFF` for `AA:BB:CC:DD:EE:FF`; its entity IDs start
with that name, for example `sensor.votronic_s_bc_eeff_battery_voltage`.

`Battery voltage` comes from the battery computer and the solar charger; the
latest value wins.

## Battery Computer / Smart Shunt

| Entity | Unit | Description |
| --- | --- | --- |
| Battery voltage | V | Main battery |
| Secondary battery voltage | V | Second battery |
| Remaining battery capacity | Ah | |
| State of charge | % | |
| Current | A | Positive while charging, negative while discharging |
| Power | W | Current times battery voltage |
| Battery nominal capacity | Ah | As configured in the battery computer |
| Charging | on/off | Current is positive |
| Discharging | on/off | Current is negative |

## Solar Charger

| Entity | Unit | Description |
| --- | --- | --- |
| Battery voltage | V | |
| PV voltage | V | Solar module |
| PV current | A | Charging current |
| PV power | W | |
| PV controller temperature | °C | `Unknown` while the controller is in standby, e.g. at night |
| Charged capacity | Ah | Total, only increases |
| Charged energy | Wh | Total, only increases |
| Battery status | | Charging phase, see `Status values` |
| PV controller status | | See `Status values` |
| Battery status bitmask | | Raw value |
| PV controller status bitmask | | Raw value |
| Controller active | on/off | Bit 3 of the PV controller status |
| Current reduction | on/off | Bit 4 of the PV controller status |
| AES active | on/off | Bit 5 of the PV controller status |

## Status values

Battery status:

| Bit | Value | Meaning |
| --- | --- | --- |
| 0 | `I phase` | Constant current |
| 1 | `U1 phase` | First constant voltage |
| 2 | `U2 phase` | Second constant voltage |
| 3 | `U3 phase` | Float |

PV controller status:

| Bit | Value | Meaning |
| --- | --- | --- |
| 3 | `Active` | Controller is active |
| 4 | `Reduced` | Controller reduces the current |
| 5 | `AES active` | AES function is active |

With no bit set the value is `Standby`, with several bits the highest one,
with only unknown bits `Unknown (0xXX)`; unknown bits next to known ones are
ignored. The `on/off` entities follow their bit directly.
