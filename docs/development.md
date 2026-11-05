# Development

## Checks

```bash
python3 -m unittest
python3 -m compileall -q custom_components tests
pip install -r requirements-dev.txt
ruff check custom_components tests
ruff format --check custom_components tests
```

### Home Assistant tests

`tests/ha` runs the integration inside Home Assistant with
[pytest-homeassistant](https://github.com/home-assistant/core/tree/dev/packages/pytest-homeassistant).
Bluetooth and D-Bus are faked. Needs Python 3.14.2 or newer:

```bash
python3 -m venv .venv-ha
.venv-ha/bin/pip install -r requirements-ha-test.txt
.venv-ha/bin/pip install $(.venv-ha/bin/python tests/ha/integration_requirements.py)
.venv-ha/bin/python -m pytest
```

- `requirements-ha-test.txt` pins only Home Assistant. pip picks the plugin
  release made for it; the plugin stays unpinned because it releases betas
  too.
- `integration_requirements.py` prints the requirements of the Bluetooth
  integration of Home Assistant. The `bluetooth` extra of the plugin leaves
  out dbus-fast outside Linux.
- For the minimum version, install `pytest-homeassistant[bluetooth]==` the
  version in `hacs.json` instead of `requirements-ha-test.txt`.
- `tests/ha` is not a package, so `unittest` skips it.

## Pre-commit hooks

gitleaks, Ruff, JSON and YAML checks and hygiene hooks run on every commit.
The gitleaks hook checks only the staged changes, so `--all-files` scans
nothing; the `secrets` job in CI scans the whole history:

```bash
pip install pre-commit
pre-commit install
pre-commit run --all-files
```

## Continuous integration

`.github/workflows/ci.yml` runs on pushes to `main`, on pull requests and
every Monday, because hassfest and HACS change their rules:

| Job | Checks |
| --- | --- |
| `test` | compileall, unit tests |
| `lint` | Ruff, duplicate keys in YAML files |
| `ha-test` | Home Assistant tests at the minimum and the current version |
| `secrets` | gitleaks over the whole history |
| `hassfest` | Home Assistant validation |
| `hacs` | HACS validation |

### Pinned tool versions

The tools are pinned, Renovate proposes updates. Not pinned are
pytest-homeassistant, see above, and the validation images
of hassfest and HACS, see below.

| What | Pinned in | Also in `.pre-commit-config.yaml` |
| --- | --- | --- |
| Runner `ubuntu-YY.MM` | `runs-on` in the workflows | |
| Python | `python-version` in `ci.yml` | |
| GitHub Actions | commit SHA in the workflows | |
| gitleaks | image tag and digest in the `secrets` job of `ci.yml` | yes |
| Ruff | `requirements-dev.txt` | yes |
| PyYAML | `requirements-dev.txt` | |
| Home Assistant | `requirements-ha-test.txt`; the minimum in `hacs.json` | |
| Hygiene hooks | | yes |

`.pre-commit-config.yaml` pins each hook to the commit of its tag, with the
tag in a `# frozen:` comment. A tool pinned in both places must have the same
version in both. To update one by hand, change both, for a hook the commit
and the comment, and run `pre-commit run --all-files`.

The hassfest and HACS actions follow their default branch. The actions are
pinned, their validation images are not, so the checks apply the current
rules of Home Assistant and HACS.

### Dependency updates

Renovate, configured in `renovate.json`:

- New pull requests open on Saturdays; others wait in the
  `Dependency Dashboard` issue.
- Major updates need a tick in the dashboard.
- Open pull requests are rebased onto `main` when it moves, so they can be
  merged one after another without `Update branch`.
- Digests of the actions, Python patches and Ruff merge themselves once CI
  passes.
- The dashboard lists every known vulnerability of a detected dependency,
  also those without a fixed version.
- Python follows Home Assistant: only patches of the minor version in
  `ci.yml` come. When the latest Home Assistant release raises its minimum
  Python version, a pull request updates `Needs Python … or newer` above. For
  a new minor version, add to it the latest patch in `python-version` in
  `ci.yml`, the next minor in `allowedVersions` of `python` in `renovate.json`
  and the new `target-version` in `pyproject.toml`.
- Every stable Home Assistant release comes as a pull request; its CI run
  is the test.
- Tools pinned in two places come in one pull request.
- New releases wait 3 days before they are proposed.
- Renovate checks the direct dependencies it detects, e.g. on PyPI, against
  osv.dev (experimental). A known vulnerability with a fixed version comes
  as a pull request at once, outside the schedule and the waiting time.
  Packages that Home Assistant pins are not covered.

## Upstream changes

The protocol comes from `components/votronic_ble` of
[syssi/esphome-votronic](https://github.com/syssi/esphome-votronic).

Last reviewed upstream commit: `188beeb03895f18b7d728628a5318fc0cef5fdca`

Renovate opens a pull request when upstream `main` moves. Review the linked
comparison, then:

- transfer the changes and push them to the Renovate branch, or
- merge it as is when `components/votronic_ble` did not change.

| Upstream | Here |
| --- | --- |
| UUIDs in `votronic_ble.h` | `const.py` |
| Frame parsing in `votronic_ble.cpp` | `parser.py`, with tests in `tests/test_parser.py` |
| `sensor.py`, `text_sensor.py` | `sensor.py` |
| `binary_sensor.py` | `binary_sensor.py` |
| Entity names | `strings.json` and `translations/*.json`; `en.json` equals `strings.json` |
| New entities | also `docs/entities.md` |

## Pairing through BlueZ

- The Bluetooth Connector bonds only in pairing mode and asks for a six-digit
  passkey. bleak's `pair()` registers no BlueZ agent, so `pairing.py` exports
  one on its own D-Bus connection and calls `Pair()` through it; BlueZ asks
  the agent of the caller.
- The connector advertises a public address without the "BR/EDR not
  supported" flag, so BlueZ connects a new device over BR/EDR, which fails.
  `PreferredBearer` `le` avoids that.
- An earlier pairing is removed first. It may be stale after `Key` was held,
  and `Pair()` of a device paired over LE tries BR/EDR and fails with a page
  timeout. Removing the config entry removes the pairing too.
- After a lost connection, `bluetooth.py` closes the old client. bleak keeps
  its D-Bus connection open until `disconnect()`, and BlueZ would deliver
  every frame twice after the reconnect.

## Testing unreleased changes

Copy `custom_components/votronic_ble` of the branch or of `main` to
`/config/custom_components/votronic_ble` and restart Home Assistant.

## Releases

1. Set `version` in `custom_components/votronic_ble/manifest.json` in a pull
   request and merge it.
2. Tag `main` with a signed tag. The signing key must be in your GitHub
   account. The tag message becomes the release notes:

   ```bash
   git switch main
   git pull
   git tag -s vX.Y.Z -m "Release notes"
   git push origin vX.Y.Z
   ```

3. `release.yml` checks that the tag is on `main`, that GitHub verifies its
   signature and that it matches the manifest version, waits until CI of the
   tagged commit has passed, then creates the GitHub release. The
   Marketplace then offers the update.

## Known limitations

- Pairing, real Bluetooth Connectors and the Marketplace are tested by hand
  only.
- Home Assistant versions between the minimum and the current one are not
  tested.
- Bluetooth proxies are not supported, see `docs/pairing.md`.
