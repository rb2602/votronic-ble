"""Duplicate keys in the JSON and YAML files of the repository.

json and PyYAML silently keep the last of two equal keys, so a duplicate in
the manifest, a translation or the CI configuration would go unnoticed. The
YAML part needs PyYAML and is skipped without it; CI runs it in the lint
job.
"""

from __future__ import annotations

import json
from pathlib import Path
import unittest

try:
    import yaml
except ImportError:
    yaml = None

ROOT = Path(__file__).resolve().parents[1]
JSON_FILES = sorted({*ROOT.glob("*.json"), *ROOT.glob("custom_components/**/*.json")})
YAML_FILES = sorted(
    {
        *ROOT.glob("*.yml"),
        *ROOT.glob(".*.yml"),
        *ROOT.glob("*.yaml"),
        *ROOT.glob(".*.yaml"),
        *ROOT.glob(".github/workflows/*.yml"),
    }
)


def _reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    keys = [key for key, _ in pairs]
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    if duplicates:
        raise ValueError(f"duplicate keys {duplicates}")
    return dict(pairs)


def _load_json(text: str) -> object:
    return json.loads(text, object_pairs_hook=_reject_duplicates)


if yaml is not None:

    class _UniqueKeyLoader(yaml.SafeLoader):
        """SafeLoader that refuses a mapping with two equal keys."""

        def construct_mapping(self, node, deep=False):
            seen = set()
            for key_node, _ in node.value:
                key = self.construct_object(key_node, deep=deep)
                if key in seen:
                    raise yaml.constructor.ConstructorError(
                        None, None, f"duplicate key {key!r}", key_node.start_mark
                    )
                seen.add(key)
            return super().construct_mapping(node, deep)


def _load_yaml(text: str) -> object:
    return yaml.load(text, Loader=_UniqueKeyLoader)


class JsonDuplicateKeyTest(unittest.TestCase):
    def test_files_have_no_duplicate_keys(self) -> None:
        self.assertIn(ROOT / "renovate.json", JSON_FILES)
        for path in JSON_FILES:
            with self.subTest(path=str(path.relative_to(ROOT))):
                _load_json(path.read_text(encoding="utf-8"))

    def test_detects_duplicate_key(self) -> None:
        with self.assertRaisesRegex(ValueError, r"duplicate keys \['name'\]"):
            _load_json('{"a": {"name": 1, "name": 2}}')


@unittest.skipIf(yaml is None, "needs PyYAML")
class YamlDuplicateKeyTest(unittest.TestCase):
    def test_files_have_no_duplicate_keys(self) -> None:
        self.assertIn(ROOT / ".github" / "workflows" / "ci.yml", YAML_FILES)
        for path in YAML_FILES:
            with self.subTest(path=str(path.relative_to(ROOT))):
                _load_yaml(path.read_text(encoding="utf-8"))

    def test_detects_duplicate_key(self) -> None:
        with self.assertRaisesRegex(yaml.YAMLError, "duplicate key 'version'"):
            _load_yaml("name: a\nversion: 1\nversion: 2\n")


if __name__ == "__main__":
    unittest.main()
