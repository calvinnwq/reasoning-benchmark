from __future__ import annotations

import sys
import unittest
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parent
sys.path.append(str(REPO_ROOT / "scripts"))

import extensions


class ReservedNamespaceTests(unittest.TestCase):
    """The hook contract reserves namespaces for future expansion packs."""

    def test_tool_use_and_multi_agent_are_reserved(self) -> None:
        self.assertIn("tool_use", extensions.RESERVED_EXTENSION_NAMESPACES)
        self.assertIn("multi_agent", extensions.RESERVED_EXTENSION_NAMESPACES)

    def test_reserved_namespaces_are_exact_strings(self) -> None:
        for namespace in extensions.RESERVED_EXTENSION_NAMESPACES:
            self.assertIsInstance(namespace, str)
            self.assertEqual(namespace, namespace.strip())
            self.assertNotEqual(namespace, "")


class ValidateExtensionsBlockTests(unittest.TestCase):
    """validate_extensions_block enforces the data-first contract."""

    def test_none_extensions_block_is_allowed(self) -> None:
        extensions.validate_extensions_block(None)

    def test_empty_extensions_block_is_allowed(self) -> None:
        extensions.validate_extensions_block({})

    def test_extensions_block_must_be_object(self) -> None:
        for value in ("tool_use", ["tool_use"], 1, True):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "extensions"):
                    extensions.validate_extensions_block(value)

    def test_unknown_namespace_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown extension namespace"):
            extensions.validate_extensions_block({"browser_use": {"enabled": False}})

    def test_namespace_keys_must_be_exact_strings(self) -> None:
        with self.assertRaisesRegex(ValueError, "extension namespace"):
            extensions.validate_extensions_block({" tool_use": {"enabled": False}})

    def test_namespace_payload_must_be_object(self) -> None:
        with self.assertRaisesRegex(ValueError, "payload must be a JSON object"):
            extensions.validate_extensions_block({"tool_use": "enabled"})

    def test_enabled_field_is_required(self) -> None:
        with self.assertRaisesRegex(ValueError, "explicit 'enabled' boolean"):
            extensions.validate_extensions_block({"multi_agent": {}})

    def test_enabled_field_must_be_boolean(self) -> None:
        with self.assertRaisesRegex(ValueError, "'enabled' must be a boolean"):
            extensions.validate_extensions_block({"tool_use": {"enabled": "no"}})

    def test_enabled_true_is_rejected_until_implementation_exists(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "tool_use.+no implementation",
        ):
            extensions.validate_extensions_block({"tool_use": {"enabled": True}})

    def test_declared_disabled_extensions_pass_validation(self) -> None:
        extensions.validate_extensions_block(
            {
                "tool_use": {"enabled": False, "notes": "reserved for M5"},
                "multi_agent": {"enabled": False},
            }
        )


if __name__ == "__main__":
    unittest.main()
