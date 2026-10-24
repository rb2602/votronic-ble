# Votronic Bluetooth for Home Assistant

Home Assistant integration for the Votronic Bluetooth Connector S-BC. It reads
the solar charger and the battery computer over Bluetooth, without an ESP32.

Independent community project, not affiliated with Votronic. The Bluetooth
protocol comes from
[syssi/esphome-votronic](https://github.com/syssi/esphome-votronic).

## Features

- Bluetooth discovery and setup in the Home Assistant UI
- Pairing with the default or your own pairing code
- Live values of the solar charger and the battery computer
- Installation and updates through HACS

## Supported devices

Tested: Bluetooth Connector S-BC with a Votronic MPP solar charger.

Untested, implemented after the upstream project: Battery Computer S and
Smart Shunt, VBCS Triple CI, VPC Jupiter. Reports in the issue tracker are
welcome.

## Requirements

- Home Assistant 2026.5 or newer
- [HACS](https://hacs.xyz)
- A Bluetooth adapter of the Home Assistant host in range of the Bluetooth
  Connector. Bluetooth proxies are not supported.

## Documentation

- [Installation](docs/installation.md)
- [Pairing](docs/pairing.md)
- [Entities](docs/entities.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Development](docs/development.md)

## Support

Report bugs in the
[issue tracker](https://github.com/rb2602/votronic-ble/issues), security
vulnerabilities privately, see [SECURITY.md](SECURITY.md).

## License

Apache License 2.0, see `LICENSE` and `NOTICE`.
