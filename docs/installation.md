# Installation

## Install

Requires [HACS](https://hacs.xyz/docs/use/).

[![Open your Home Assistant instance and open the Votronic Bluetooth repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=rb2602&repository=votronic-ble&category=integration)

1. Click the button and add the repository in HACS.
2. Click `Download`.
3. Restart Home Assistant.
4. Set up the integration, see [Pairing](pairing.md).

If the button does not work: in HACS, menu `Custom repositories`, URL
`https://github.com/rb2602/votronic-ble`, type `Integration`.

Without HACS: copy `custom_components/votronic_ble` from a
[release](https://github.com/rb2602/votronic-ble/releases) to
`/config/custom_components/votronic_ble` and restart Home Assistant.

## Update

HACS shows new versions under `Settings -> System -> Updates`. Install, then
restart Home Assistant.

## Uninstall

1. Remove `Votronic Bluetooth` under `Settings -> Devices & services`.
2. Remove `Votronic Bluetooth` in HACS.
3. Restart Home Assistant.
