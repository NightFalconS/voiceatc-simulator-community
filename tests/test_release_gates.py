import importlib.util
import json
import sys
import tempfile
import unittest
import zipfile
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


GATES = _load("release_gates", TOOLS_DIR / "release_gates.py")
RELEASE = _load("community_release_manifest", TOOLS_DIR / "community_release_manifest.py")
RELEASE_TESTS = _load("test_community_release_manifest", REPO_ROOT / "tests" / "test_community_release_manifest.py")

SPEC_GATES = {
    "schema_version": 1,
    "gates": [
        {"dataset": "color_profiles", "kind": "panels", "requires": ["color_profiles.panels"]},
        {"dataset": "routes", "lane": "next", "channels": ["closed-beta"]},
        {
            "dataset": "mva",
            "path": "E/ED/EDDM/mva.json",
            "requires": ["community.v3_feeds", "color_profiles.panels"],
            "channels": ["closed-beta", "open-beta"],
        },
    ],
}


def _file(repo_path: str) -> dict[str, object]:
    return {"repo_path": repo_path, "sha256": "0" * 64, "size_bytes": 1}


class GateFileValidationTests(unittest.TestCase):
    def test_spec_example_and_empty_list_are_valid(self) -> None:
        self.assertEqual(len(GATES.validate_gates(SPEC_GATES)), 3)
        self.assertEqual(GATES.validate_gates({"schema_version": 1, "gates": []}), [])

    def test_rejects_malformed_gates(self) -> None:
        bad_gates = [
            {"dataset": "mva", "path": "X/mva.json", "kind": "mva", "channels": ["stable"]},
            {"dataset": "mva", "path": "X/mva.json"},
            {"dataset": "mva", "path": "X/mva.json", "channels": ["beta"]},
            {"dataset": "mva", "path": "X/mva.json", "min_game_version": "0.6.2.380"},
            {"dataset": "mva", "path": "X/mva.json", "requires": []},
            {"dataset": "mva", "path": "X/mva.json", "requires": "color_profiles.panels"},
            {"dataset": "mva", "path": "X/mva.json", "requires": ["panels"]},
            {"dataset": "mva", "path": "X/mva.json", "requires": ["Color_Profiles.panels"]},
            {"dataset": "mva", "path": "X/mva.json", "requires": ["color-profiles.panels"]},
            {"dataset": "mva", "path": "X/mva.json", "requires": ["color_profiles."]},
            {"dataset": "mva", "path": "X/mva.json", "requires": ["a." + "b" * 63]},
            {"dataset": "mva", "path": "X/mva.json", "requires": ["a.b", "a.b"]},
            {"dataset": "mva", "lane": "next", "channels": ["closed-beta"]},
            {"dataset": "routes", "path": "ROUTES/x.tsv", "channels": ["closed-beta"]},
            {"dataset": "mva", "path": "../x", "channels": ["stable"]},
            {"dataset": "mva", "path": "X/mva.json", "channels": ["stable"], "note": "x"},
            {"dataset": "color_profiles", "kind": "Panels", "channels": ["stable"]},
        ]
        for gate in bad_gates:
            with self.subTest(gate=gate), self.assertRaises(ValueError):
                GATES.validate_gates({"schema_version": 1, "gates": [gate]})
        with self.assertRaises(ValueError):
            GATES.validate_gates({"schema_version": 2, "gates": []})
        with self.assertRaises(ValueError):
            GATES.validate_gates({"schema_version": 1, "gates": [], "extra": 1})

    def test_capability_names_are_lowercase_dotted_and_at_most_64_characters(self) -> None:
        for good in ("color_profiles.panels", "skins.catalog", "community.v3_feeds", "a.b.c", "x1.y_2", "a." + "b" * 62):
            with self.subTest(name=good):
                self.assertEqual(GATES.validate_capability(good), good)
        for bad in ("panels", "A.b", "a.B", "a-b.c", "a..b", ".a.b", "a.b.", "a b.c", "", 3, None, "a." + "b" * 63):
            with self.subTest(name=bad), self.assertRaises(ValueError):
                GATES.validate_capability(bad)

    def test_committed_files_are_valid(self) -> None:
        GATES.load_gates(REPO_ROOT)
        self.assertFalse((REPO_ROOT / "release" / "live_versions.json").exists())

    def test_no_version_support_remains(self) -> None:
        self.assertFalse(hasattr(GATES, "parse_version"))
        self.assertFalse(hasattr(GATES, "load_live_versions"))
        self.assertNotIn("min_game_version", GATES.GATE_RULES)


class GateDecisionTests(unittest.TestCase):
    def test_default_keeps_only_ungated_or_all_channel_content_without_requirements(self) -> None:
        visible = GATES.is_default_visible
        self.assertTrue(visible({}))
        self.assertTrue(visible({"channels": ["stable", "open-beta", "closed-beta"]}))
        self.assertTrue(visible({"channels": ["closed-beta", "stable", "open-beta"]}))
        self.assertFalse(visible({"channels": ["closed-beta", "open-beta"]}))
        self.assertFalse(visible({"channels": ["closed-beta"]}))
        self.assertFalse(visible({"requires": ["skins.catalog"]}))
        self.assertFalse(visible({"requires": ["skins.catalog"], "channels": ["stable", "open-beta", "closed-beta"]}))

    def test_ungated_entries_come_back_unchanged(self) -> None:
        entries = {"LEMD": _file("L/LE/LEMD/mva.json"), "EHAM": _file("E/EH/EHAM/mva.json")}
        result = GATES.apply_gates("mva", entries, gates=[])
        self.assertEqual(result["default"], entries)
        self.assertEqual([entry["id"] for entry in result["v3_entries"]], ["LEMD", "EHAM"])

    def test_path_gate_removes_the_entry_from_default_and_marks_v3(self) -> None:
        gates = GATES.validate_gates(SPEC_GATES)
        entries = {"EDDM": _file("E/ED/EDDM/mva.json"), "LEMD": _file("L/LE/LEMD/mva.json")}
        result = GATES.apply_gates("mva", entries, gates=gates)
        self.assertEqual(list(result["default"]), ["LEMD"])
        eddm = result["v3_entries"][0]
        self.assertEqual(eddm["id"], "EDDM")
        self.assertEqual(eddm["requires"], ["community.v3_feeds", "color_profiles.panels"])
        self.assertEqual(eddm["channels"], ["open-beta", "closed-beta"])
        self.assertNotIn("requires", result["v3_entries"][1])

    def test_kind_gate_drops_only_that_file_including_alias_copies(self) -> None:
        gates = GATES.validate_gates(SPEC_GATES)
        profiles = {
            "K/KA": {"files": {"colors": _file("K/KA/colors.json"), "panels": _file("K/KA/panels.json")}},
            "L/LE": {"files": {"colors": _file("L/LE/colors.json")}},
        }
        result = GATES.apply_gates(
            "color_profiles", profiles, gates=gates, required_kinds=("colors",)
        )
        self.assertEqual(result["default"]["K/KA"], {"files": {"colors": _file("K/KA/colors.json")}})
        self.assertIs(result["default"]["L/LE"], profiles["L/LE"])
        v3_panels = result["v3_entries"][0]["files"]["panels"]
        self.assertEqual(v3_panels["requires"], ["color_profiles.panels"])
        self.assertEqual(GATES.entry_repo_paths(result["default"]), ["K/KA/colors.json", "L/LE/colors.json"])

    def test_gating_a_required_kind_removes_the_whole_entry(self) -> None:
        gates = [{"dataset": "color_profiles", "path": "L/LE/colors.json", "channels": ["closed-beta"]}]
        profiles = {"L/LE": {"files": {"colors": _file("L/LE/colors.json"), "style": _file("L/LE/style.json")}}}
        result = GATES.apply_gates(
            "color_profiles", profiles, gates=gates, required_kinds=("colors",)
        )
        self.assertEqual(result["default"], {})
        self.assertEqual(len(result["v3_entries"]), 1)

    def test_path_gate_matches_the_alias_source(self) -> None:
        gates = [{"dataset": "color_profiles", "path": "K/panels.json", "requires": ["color_profiles.panels"]}]
        profiles = {"K/KA": {"files": {"colors": _file("K/KA/colors.json"), "panels": _file("K/KA/panels.json")}}}
        result = GATES.apply_gates(
            "color_profiles",
            profiles,
            gates=gates,
            archive_sources={"K/KA/colors.json": "K/colors.json", "K/KA/panels.json": "K/panels.json"},
            required_kinds=("colors",),
        )
        self.assertNotIn("panels", result["default"]["K/KA"]["files"])

    def test_all_channel_gate_keeps_entry_in_default(self) -> None:
        gates = [{"dataset": "mva", "path": "L/*", "channels": ["stable", "open-beta", "closed-beta"]}]
        entries = {"LEMD": _file("L/LE/LEMD/mva.json")}
        result = GATES.apply_gates("mva", entries, gates=gates)
        self.assertEqual(result["default"], entries)
        self.assertEqual(result["v3_entries"][0]["channels"], ["stable", "open-beta", "closed-beta"])

    def test_requirements_from_several_gates_are_merged_without_duplicates(self) -> None:
        gates = [
            {"dataset": "mva", "path": "L/*", "requires": ["skins.catalog"]},
            {"dataset": "mva", "path": "L/LE/*", "requires": ["color_profiles.panels", "skins.catalog"]},
        ]
        entries = {"LEMD": _file("L/LE/LEMD/mva.json")}
        result = GATES.apply_gates("mva", entries, gates=gates)
        self.assertEqual(result["default"], {})
        self.assertEqual(result["v3_entries"][0]["requires"], ["skins.catalog", "color_profiles.panels"])


class ProducerGateTests(unittest.TestCase):
    def _bundle(self, root: Path, out: str) -> dict[str, object]:
        return RELEASE.build_release_bundle(
            output_dir=root / out,
            release_tag="daily-2026-10-01",
            published_at="2026-10-01T00:00:00Z",
            commit_sha="abc123",
            download_repo="lainoa-software/voiceatc-simulator-community",
            root=root,
        )

    def _gate(self, root: Path, gates: list[dict[str, object]]) -> None:
        RELEASE_TESTS.write_json(root / ".voiceatc" / "gates.json", {"schema_version": 1, "gates": gates})

    def test_empty_gate_list_output_is_byte_identical_to_no_gates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            RELEASE_TESTS.build_fixture_repo(root)
            before = self._bundle(root, "a")
            self._gate(root, [])
            after = self._bundle(root, "b")
            self.assertEqual(before["manifests"], after["manifests"])
            for key in ("mva_zip", "runway_configs_zip", "sector_data_zip", "misc_drawings_zip", "color_profiles_zip"):
                self.assertEqual(
                    Path(before["assets"][key]["path"]).read_bytes(),
                    Path(after["assets"][key]["path"]).read_bytes(),
                )

    def test_gated_entries_leave_default_but_stay_in_v3_and_full_zip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            RELEASE_TESTS.build_fixture_repo(root)
            ungated = self._bundle(root, "a")
            self._gate(
                root,
                [
                    {"dataset": "mva", "path": "L/LE/LECB/*", "requires": ["community.v3_feeds"]},
                    {"dataset": "color_profiles", "kind": "style", "channels": ["closed-beta"]},
                ],
            )
            bundle = self._bundle(root, "b")
            mva = bundle["manifests"]["mva"]
            self.assertEqual(sorted(mva["airports"]), ["LEMD"])
            self.assertEqual(mva["airport_count"], 1)
            with zipfile.ZipFile(bundle["assets"]["mva_zip"]["path"]) as archive:
                self.assertEqual(archive.namelist(), ["L/LE/LECM/LECM_R2/MADRID_TMA/mva.json"])
            with zipfile.ZipFile(bundle["assets"]["mva_full_zip"]["path"]) as archive:
                self.assertEqual(len(archive.namelist()), 2)
            v3_mva = bundle["v3_manifests"]["mva"]
            self.assertEqual(v3_mva["schema_version"], 3)
            self.assertEqual(v3_mva["asset_name"], "mva-2602-full.zip")
            self.assertEqual(v3_mva["sha256"], bundle["assets"]["mva_full_zip"]["sha256"])
            lebl = next(entry for entry in v3_mva["entries"] if entry["id"] == "LEBL")
            self.assertEqual(lebl["requires"], ["community.v3_feeds"])

            colors = bundle["manifests"]["color_profiles"]["profiles"]
            self.assertTrue(all(set(profile["files"]) == {"colors"} for profile in colors.values()))
            with zipfile.ZipFile(bundle["assets"]["color_profiles_zip"]["path"]) as archive:
                self.assertFalse(any(name.endswith("style.json") for name in archive.namelist()))
            # Datasets without gates are untouched.
            self.assertEqual(bundle["manifests"]["runway_configs"], ungated["manifests"]["runway_configs"])

    def test_gates_need_no_other_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            RELEASE_TESTS.build_fixture_repo(root)
            RELEASE_TESTS.write_json(
                root / ".voiceatc" / "gates.json",
                {"schema_version": 1, "gates": [{"dataset": "mva", "path": "L/*", "channels": ["closed-beta"]}]},
            )
            bundle = self._bundle(root, "a")
            self.assertEqual(bundle["manifests"]["mva"]["airports"], {})


if __name__ == "__main__":
    unittest.main()
