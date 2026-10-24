# Pairing

The Bluetooth Connector sends its data only to paired devices.

## Pairing mode

- Press the `Key` button on the Bluetooth Connector briefly. The yellow and
  green LEDs blink alternately for up to 3 minutes. Pair within this time.
- If the LEDs do not blink alternately, hold `Key` for 3 seconds. This
  deletes all pairings, also those of phones and tablets. Then press it
  briefly.

The pairing code is `173928`, or your own code if you set one.

## Pair in Home Assistant

1. `Settings -> Devices & services -> Add integration -> Votronic Bluetooth`
2. Select the Bluetooth Connector.
3. Start pairing mode.
4. Confirm.

If the Bluetooth Connector rejects `173928`, Home Assistant asks for your own
code.

## Bluetooth proxies

Not supported. Only the Bluetooth adapter of Home Assistant is paired with the
Bluetooth Connector. If a proxy has a better signal, Home Assistant may
connect through it, and then no data arrives.
