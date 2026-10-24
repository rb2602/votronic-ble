# Troubleshooting

## Votronic Bluetooth is not found in HACS

Add the repository by hand, see [Installation](installation.md#install).

## Votronic Bluetooth is missing when adding an integration

Restart Home Assistant after the download. The folder must be
`/config/custom_components/votronic_ble`.

## No device is found

- Check that Bluetooth works in Home Assistant.
- Move the Bluetooth Connector closer to the Home Assistant host.

## Pairing fails

The dialog names the reason:

| Message | What to do |
| --- | --- |
| Not in pairing mode | Start [pairing mode](pairing.md#pairing-mode) and confirm while the LEDs blink alternately. |
| Pairing code rejected | Check your own code. |
| Connection or pairing failed | Move the Bluetooth Connector closer and retry. |
| Bluetooth proxy | Not supported, see [Bluetooth proxies](pairing.md#bluetooth-proxies). |

## Device is reported as unsupported

The device is not a Votronic Bluetooth Connector, or its firmware is
different. Report it with a debug log, see `Reporting an issue`.

## Device is already configured

Remove the existing `Votronic Bluetooth` entry first.

## Entities are missing or unavailable

- Entities appear with the first data of their device: without a battery
  computer there are no battery entities.
- Entities are `unavailable` while the Bluetooth Connector is disconnected
  and when their device sent no data for 60 seconds. The integration
  reconnects every 30 seconds.

## No update is offered

In HACS, open `Votronic Bluetooth` and select `Update information` in the menu.

## The old version is still running

Restart Home Assistant.

## Reporting an issue

Report bugs in the
[issue tracker](https://github.com/rb2602/votronic-ble/issues), security
vulnerabilities privately, see [SECURITY.md](../SECURITY.md).

Include the Home Assistant version, the integration version, the Votronic
devices on the Bluetooth Connector and a debug log:

```yaml
logger:
  logs:
    custom_components.votronic_ble: debug
```

Replace the address of your Bluetooth Connector in the log, e.g. with
`AA:BB:CC:DD:EE:FF`.
