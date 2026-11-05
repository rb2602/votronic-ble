"""Constants for the Votronic integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "votronic_ble"
CONF_PAIRING_CODE: Final = "pairing_code"

# Pairing code of the Bluetooth Connector as delivered, see docs/pairing.md.
DEFAULT_PAIRING_CODE: Final = 173928

# Followed by the last four hex digits of the address.
DEVICE_NAME_PREFIX: Final = "Votronic S-BC"
DEFAULT_RECONNECT_SECONDS: Final = 30
# A value is unavailable when no frame of its type arrived for this long.
DATA_TIMEOUT_SECONDS: Final = 60

VOTRONIC_NAME_PREFIX: Final = "votronic"

# From the upstream ESPHome project, see docs/development.md.
SERVICE_MONITORING_UUID: Final = "d0cb6aa7-8548-46d0-99f8-2d02611e5270"
CHAR_BATTERY_COMPUTER_UUID: Final = "9a082a4e-5bcc-4b1d-9958-a97cfccfa5ec"
CHAR_SOLAR_CHARGER_UUID: Final = "971ccec2-521d-42fd-b570-cf46fe5ceb65"

ATTRIBUTION: Final = "Protocol based on syssi/esphome-votronic"
