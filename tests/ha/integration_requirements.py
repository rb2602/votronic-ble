"""Print the requirements of the Bluetooth integration of the installed Home Assistant."""

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
    return sorted(found)


if __name__ == "__main__":
    print("\n".join(requirements()))
