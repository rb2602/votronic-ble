"""Structural checks for strings.json and the translation files."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

_INTEGRATION = Path(__file__).resolve().parents[1] / "custom_components" / "votronic_ble"
_STRINGS = _INTEGRATION / "strings.json"
_TRANSLATIONS = sorted((_INTEGRATION / "translations").glob("*.json"))


def _key_paths(data: object, prefix: str = "") -> set[str]:
    if not isinstance(data, dict):
        return {prefix}
    return set().union(*(_key_paths(value, f"{prefix}/{key}") for key, value in data.items()))


class TranslationTest(unittest.TestCase):
    def test_all_json_files_parse(self) -> None:
        for path in _INTEGRATION.rglob("*.json"):
            with self.subTest(path=path.name):
                json.loads(path.read_text(encoding="utf-8"))

    def test_english_translation_equals_strings(self) -> None:
        # Home Assistant loads translations/en.json at runtime and strings.json
        # is the source; both must be identical.
        self.assertEqual(
            (_INTEGRATION / "translations" / "en.json").read_bytes(), _STRINGS.read_bytes()
        )

    def test_translations_have_the_same_keys(self) -> None:
        expected = _key_paths(json.loads(_STRINGS.read_text(encoding="utf-8")))
        self.assertTrue(_TRANSLATIONS)
        for path in _TRANSLATIONS:
            with self.subTest(language=path.stem):
                actual = _key_paths(json.loads(path.read_text(encoding="utf-8")))
                self.assertEqual(actual, expected)

    def test_manifest_version_is_semver(self) -> None:
        manifest = json.loads((_INTEGRATION / "manifest.json").read_text(encoding="utf-8"))
        self.assertRegex(manifest["version"], r"^\d+\.\d+\.\d+$")
        self.assertEqual(manifest["domain"], "votronic_ble")
