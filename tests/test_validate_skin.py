import hashlib
import importlib.util
import io
import json
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


MODULE = _load("validate_skin", TOOLS_DIR / "validate_skin.py")
CONTRACT_DIR = TOOLS_DIR / "interface_contract"
TOP_SLOTS = {
    "left": ["airport", "qnh", "tl", "rwy", "radio"],
    "right": ["com", "tfc", "vprof", "clock", "warp", "pause", "settings"],
}


class VendoredContractTests(unittest.TestCase):
    """The vendored schema and Generic are byte-for-byte the pinned game commit's."""

    def test_vendored_files_match_their_pinned_hashes(self) -> None:
        contract = json.loads((CONTRACT_DIR / "contract.json").read_text(encoding="utf-8"))
        self.assertRegex(contract["game_commit"], r"^[0-9a-f]{40}$")
        for name, digest in contract["files"].items():
            with self.subTest(file=name):
                data = (CONTRACT_DIR / name).read_bytes()
                self.assertEqual(digest, hashlib.sha256(data).hexdigest(),
                                 f"{name} differs from game commit {contract['game_commit']}; "
                                 "re-run tools/sync_interface_contract.py instead of editing it")

    def test_contract_lists_the_slot_features_and_capabilities(self) -> None:
        contract = MODULE.load_contract()
        self.assertIn("settings", contract["features"]["top"])
        self.assertIn("maps", contract["features"]["bottom"])
        self.assertIn("interface.top.dcb_grid", contract["capabilities"])


class StrictErrorsTests(unittest.TestCase):
    def errors(self, raw: dict, root: Path | None = None) -> list[str]:
        return MODULE.strict_errors(raw, root=root or REPO_ROOT)

    def test_generic_and_a_three_colour_recolour_are_valid(self) -> None:
        self.assertEqual([], self.errors(MODULE.generic()))
        recolour = {"tokens": {"colors": {"bar": "10141E", "panel": "0C1018", "accent": "3A5A8C"}}}
        self.assertEqual([], self.errors(recolour))

    def test_unknown_key_has_its_path_and_a_hint(self) -> None:
        self.assertEqual(
            ["primitives.list.row_heigth: unknown key (did you mean 'row_height'?)"],
            self.errors({"primitives": {"list": {"row_heigth": 30}}}),
        )

    def test_values_are_checked_against_the_schema(self) -> None:
        errors = self.errors({
            "tokens": {"colors": {"bar": "#102030"}, "fonts": {"text": "arial"}, "type": {"title": 99},
                       "case": "lower"},
        })
        self.assertIn("tokens.colors.bar: '#102030' is not a valid value", errors)
        self.assertTrue(any(e.startswith("tokens.fonts.text: 'arial' is not one of") for e in errors), errors)
        self.assertIn("tokens.type.title: 99 is outside 6..48", errors)
        self.assertTrue(any(e.startswith("tokens.case: 'lower' is not one of") for e in errors), errors)

    def test_integer_rejects_fractions_and_booleans(self) -> None:
        errors = self.errors({"primitives": {"list": {"row_height": 24.5, "separation": True}}})
        self.assertIn("primitives.list.row_height: expected integer", errors)
        self.assertIn("primitives.list.separation: expected integer", errors)

    def test_role_references_must_exist_in_the_resolved_tokens(self) -> None:
        self.assertEqual(
            ["primitives.button.states.normal.text: no colors role 'valuee' (did you mean 'value'?)"],
            self.errors({"primitives": {"button": {"states": {"normal": {"text": "valuee"}}}}}),
        )
        own_role = {"tokens": {"colors": {"brass": "B08D57"}},
                    "primitives": {"button": {"states": {"normal": {"text": "brass"}}}}}
        self.assertEqual([], self.errors(own_role))

    def test_parity_every_feature_exactly_once(self) -> None:
        slots = {"left": ["airport", "qnh", "tl", "rwy", "radio", "radio"],
                 "right": ["com", "tfc", "vprof", "clock", "warp", "pause"]}
        errors = self.errors({"components": {"top": {"slots": slots}}})
        self.assertIn("components.top.slots.left: 'radio' is placed twice", errors)
        self.assertIn("components.top.slots: 'settings' is missing", errors)

    def test_slot_names_and_feature_ids_get_hints(self) -> None:
        slots = {"lefft": TOP_SLOTS["left"], "right": [*TOP_SLOTS["right"][:-1], "setings"]}
        errors = self.errors({"components": {"top": {"slots": slots}}})
        self.assertIn("components.top.slots.lefft: not a slot of top cell_row (left, right) "
                      "(did you mean 'left'?)", errors)
        self.assertIn("components.top.slots.right: 'setings' is not a top feature "
                      "(did you mean 'settings'?)", errors)

    def test_dock_modes_need_the_top_dcb_grid(self) -> None:
        errors = self.errors({"components": {"wpt": {"mode": "dock_strip"},
                                             "bottom": {"mode": "merged_into_top"}}})
        self.assertIn("components.wpt.mode: dock_strip needs components.top.mode dcb_grid", errors)
        self.assertIn("components.bottom.mode: merged_into_top needs components.top.mode dcb_grid", errors)

    def test_close_cell_needs_the_top_strip_bar(self) -> None:
        self.assertEqual(["primitives.window.close: cell needs top_strip bar"],
                         self.errors({"primitives": {"window": {"close": "cell"}}}))

    def test_an_unknown_mode_is_a_missing_capability_with_a_hint(self) -> None:
        self.assertEqual(
            ["needs capability interface.radio.status_lines, which this build lacks "
             "(did you mean 'status_line'?)"],
            self.errors({"components": {"radio": {"mode": "status_lines"}}}),
        )

    def test_a_mode_change_drops_the_base_slots(self) -> None:
        errors = self.errors({"components": {"top": {"mode": "dcb_grid"}}})
        self.assertEqual([], errors)

    def test_extends_resolves_regional_and_catalog_skins_in_the_repository(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "L" / "LE").mkdir(parents=True)
            base = {"tokens": {"colors": {"brass": "B08D57"}}}
            (root / "L" / "LE" / "panels.json").write_text(json.dumps(base), encoding="utf-8")
            child = {"extends": "scope:L/LE",
                     "primitives": {"button": {"states": {"normal": {"text": "brass"}}}}}
            self.assertEqual([], self.errors(child, root))
            self.assertEqual(["extends: 'skin:nope' is not generic, scope:<path> or skin:<id> "
                              "in this repository"], self.errors({"extends": "skin:nope"}, root))

    def test_the_regional_skins_are_valid(self) -> None:
        for path in (REPO_ROOT / "L" / "LE" / "panels.json", REPO_ROOT / "K" / "panels.json"):
            with self.subTest(path=path):
                raw = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual([], self.errors(raw))
                self.assertEqual("generic", raw.get("extends"))


class GuideExamplesTests(unittest.TestCase):
    def test_every_json_example_in_the_modding_guide_is_valid(self) -> None:
        guide = "".join((REPO_ROOT / "documentation" / page).read_text(encoding="utf-8")
                        for page in ("skins-modding.md", "skins-catalog.md",
                                     "session-skins-panels-json.md"))
        blocks = re.findall(r"```json\n(.*?)```", guide, re.S)
        self.assertGreaterEqual(len(blocks), 7)
        for block in blocks:
            raw = json.loads(block)
            raw.pop("$schema", None)
            with self.subTest(name=raw.get("name")):
                self.assertEqual([], MODULE.strict_errors(raw, root=REPO_ROOT))


class CliTests(unittest.TestCase):
    def run_cli(self, *paths: Path) -> tuple[int, str]:
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(out):
            code = MODULE.main([str(path) for path in paths])
        return code, out.getvalue()

    def test_cli_reports_each_file_and_fails_on_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "good.json"
            good.write_text(json.dumps({"tokens": {"case": "upper"}}), encoding="utf-8")
            bad = Path(tmp) / "bad.json"
            bad.write_text(json.dumps({"tokens": {"colours": {}}}), encoding="utf-8")
            broken = Path(tmp) / "broken.json"
            broken.write_text('{"tokens": {', encoding="utf-8")
            code, text = self.run_cli(good, bad, broken)
        self.assertEqual(1, code)
        self.assertIn("good.json: OK", text)
        self.assertIn("tokens.colours: unknown key (did you mean 'colors'?)", text)
        self.assertIn("broken.json: invalid JSON", text)

    def test_cli_passes_valid_files(self) -> None:
        code, text = self.run_cli(REPO_ROOT / "K" / "panels.json")
        self.assertEqual(0, code, text)


if __name__ == "__main__":
    unittest.main()
