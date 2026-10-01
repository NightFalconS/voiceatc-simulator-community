import importlib.util
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("skin_reference", REPO_ROOT / "tools" / "skin_reference.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class SkinReferenceTests(unittest.TestCase):
    def test_the_reference_page_matches_the_vendored_schema(self) -> None:
        page = (REPO_ROOT / "documentation" / "skins-reference.md").read_text(encoding="utf-8")
        self.assertEqual(MODULE.render(), page,
                         "documentation/skins-reference.md is stale: run python tools/skin_reference.py")

    def test_every_schema_key_is_listed(self) -> None:
        page = MODULE.render()
        for key in ("`tokens.colors.radio_rx_text`", "`primitives.bar_cell.value_tint`",
                    "`components.com.widths.log_height`", "`components.top.mode`", "`blend_amount`"):
            with self.subTest(key=key):
                self.assertIn(key, page)


if __name__ == "__main__":
    unittest.main()
