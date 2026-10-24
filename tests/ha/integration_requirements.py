"""Print the Python requirements of the Home Assistant integrations Votronic uses.

The homeassistant package does not install the requirements of its built-in
integrations; Home Assistant installs them at runtime. The tests need those
of bluetooth and the integrations it depends on, in the versions the
installed Home Assistant pins in their manifests:

    pip install $(python tests/ha/integration_requirements.py)
"""

from __future__ import annotations

import json
from pathlib import Path

import homeassistant.components

COMPONENTS = Path(homeassistant.components.__file__).parent
INTEGRATION = Path(__file__).resolve().parents[2] / "custom_components" / "votronic_ble"
MANIFEST = INTEGRATION / "manifest.json"


def _manifest(domain: str) -> dict:
    return json.loads((COMPONENTS / domain / "manifest.json").read_text())


def requirements() -> list[str]:
    """Return the requirements of the dependency tree, sorted."""

    seen: set[str] = set()
    found: set[str] = set()
    pending = [*json.loads(MANIFEST.read_text())["dependencies"], "bluetooth"]
    while pending:
        domain = pending.pop()
        if domain in seen:
            continue
        seen.add(domain)
        manifest = _manifest(domain)
        found.update(manifest.get("requirements", []))
        pending.extend(manifest.get("dependencies", []))
    if "usb" in seen:
        # usb imports aioesphomeapi through serialx in some releases, e.g.
        # 2026.5, without declaring it; take the version esphome pins.
        found.update(
            requirement
            for requirement in _manifest("esphome")["requirements"]
            if requirement.startswith("aioesphomeapi")
        )
    return sorted(found)


if __name__ == "__main__":
    print("\n".join(requirements()))
