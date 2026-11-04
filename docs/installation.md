# Installation

## Install

From Home Assistant 2026.11 through the Marketplace, before through
[HACS](https://hacs.xyz/docs/use/). The button opens the repository in either.

[![Open your Home Assistant instance and open the Votronic Bluetooth repository in the Marketplace or HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=rb2602&repository=votronic-ble&category=integration)

1. Click the button.
2. Click `Install` in the Marketplace, `Download` in HACS.
3. HACS only: restart Home Assistant.
4. Set up the integration, see [Pairing](pairing.md).

If the button does not work, search for `Votronic Bluetooth` under
`Settings -> Marketplace` or in HACS.

Without either: copy `custom_components/votronic_ble` from a
[release](https://github.com/rb2602/votronic-ble/releases) to
`/config/custom_components/votronic_ble` and restart Home Assistant.

## Update

New versions appear under `Settings -> System -> Updates`. Install, then
restart Home Assistant.

## Uninstall

1. Remove `Votronic Bluetooth` under `Settings -> Devices & services`.
2. Uninstall `Votronic Bluetooth` in the Marketplace or remove it in HACS.
3. Restart Home Assistant.
