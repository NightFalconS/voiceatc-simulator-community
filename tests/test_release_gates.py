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

LIVE = {"stable": "0.6.1.24", "open-beta": "0.6.2.204", "closed-beta": "0.6.2.374"}
LIVE_FILE = {**LIVE, "updated_at": "2026-10-01T00:00:00Z"}
SPEC_GATES = {
    "schema_version": 1,
    "gates": [
        {"dataset": "color_profiles", "kind": "panels", "min_game_version": "0.6.2.380"},
        {"dataset": "routes", "lane": "next", "channels": ["closed-beta"]},
        {
            "dataset": "mva",
            "path": "E/ED/EDDM/mva.json",
            "min_game_version": "0.6.2.400",
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
            {"dataset": "mva", "path": "X/mva.json", "min_game_version": "0.6.2"},
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

    def test_live_versions_need_every_channel_and_a_timestamp(self) -> None:
        self.assertEqual(GATES.validate_live_versions(LIVE_FILE), LIVE)
        for broken in (
            {k: v for k, v in LIVE_FILE.items() if k != "open-beta"},
            {**LIVE_FILE, "stable": "0.6.1"},
            {**LIVE_FILE, "updated_at": "today"},
            {**LIVE_FILE, "dev": "0.0.0.1"},
        ):
            with self.subTest(payload=broken), self.assertRaises(ValueError):
                GATES.validate_live_versions(broken)

    def test_committed_files_are_valid(self) -> None:
        GATES.load_gates(REPO_ROOT)
        GATES.load_live_versions(REPO_ROOT)

    def test_versions_compare_numerically(self) -> None:
        self.assertLess(GATES.parse_version("0.6.2.99"), GATES.parse_version("0.6.2.380"))
        self.assertLess(GATES.parse_version("0.6.1.24"), GATES.parse_version("0.6.2.0"))


class GateDecisionTests(unittest.TestCase):
    def test_default_keeps_only_what_every_live_channel_passes(self) -> None:
        passes = GATES.passes_every_live_channel
        self.assertTrue(passes({"min_game_version": "0.6.1.24"}, LIVE))
        self.assertFalse(passes({"min_game_version": "0.6.1.25"}, LIVE))
        self.assertFalse(passes({"channels": ["closed-beta", "open-beta"]}, LIVE))
        self.assertTrue(passes({"channels": ["stable", "open-beta", "closed-beta"]}, LIVE))

    def test_ungated_entries_come_back_unchanged(self) -> None:
        entries = {"LEMD": _file("L/LE/LEMD/mva.json"), "EHAM": _file("E/EH/EHAM/mva.json")}
        result = GATES.apply_gates("mva", entries, gates=[], live_versions=LIVE)
        self.assertEqual(result["default"], entries)
        self.assertEqual([entry["id"] for entry in result["v3_entries"]], ["LEMD", "EHAM"])

    def test_path_gate_removes_the_entry_from_default_and_marks_v3(self) -> None:
        gates = GATES.validate_gates(SPEC_GATES)
        entries = {"EDDM": _file("E/ED/EDDM/mva.json"), "LEMD": _file("L/LE/LEMD/mva.json")}
        result = GATES.apply_gates("mva", entries, gates=gates, live_versions=LIVE)
        self.assertEqual(list(result["default"]), ["LEMD"])
        eddm = result["v3_entries"][0]
        self.assertEqual(eddm["id"], "EDDM")
        self.assertEqual(eddm["min_game_version"], "0.6.2.400")
        self.assertEqual(eddm["channels"], ["open-beta", "closed-beta"])
        self.assertNotIn("min_game_version", result["v3_entries"][1])

    def test_kind_gate_drops_only_that_file_including_alias_copies(self) -> None:
        gates = GATES.validate_gates(SPEC_GATES)
        profiles = {
            "K/KA": {"files": {"colors": _file("K/KA/colors.json"), "panels": _file("K/KA/panels.json")}},
            "L/LE": {"files": {"colors": _file("L/LE/colors.json")}},
        }
        result = GATES.apply_gates(
            "color_profiles", profiles, gates=gates, live_versions=LIVE, required_kinds=("colors",)
        )
        self.assertEqual(result["default"]["K/KA"], {"files": {"colors": _file("K/KA/colors.json")}})
        self.assertIs(result["default"]["L/LE"], profiles["L/LE"])
        v3_panels = result["v3_entries"][0]["files"]["panels"]
        self.assertEqual(v3_panels["min_game_version"], "0.6.2.380")
        self.assertEqual(GATES.entry_repo_paths(result["default"]), ["K/KA/colors.json", "L/LE/colors.json"])

    def test_gating_a_required_kind_removes_the_whole_entry(self) -> None:
        gates = [{"dataset": "color_profiles", "path": "L/LE/colors.json", "channels": ["closed-beta"]}]
        profiles = {"L/LE": {"files": {"colors": _file("L/LE/colors.json"), "style": _file("L/LE/style.json")}}}
        result = GATES.apply_gates(
            "color_profiles", profiles, gates=gates, live_versions=LIVE, required_kinds=("colors",)
        )
        self.assertEqual(result["default"], {})
        self.assertEqual(len(result["v3_entries"]), 1)

    def test_path_gate_matches_the_alias_source(self) -> None:
        gates = [{"dataset": "color_profiles", "path": "K/panels.json", "min_game_version": "0.6.2.380"}]
        profiles = {"K/KA": {"files": {"colors": _file("K/KA/colors.json"), "panels": _file("K/KA/panels.json")}}}
        result = GATES.apply_gates(
            "color_profiles",
            profiles,
            gates=gates,
            live_versions=LIVE,
            archive_sources={"K/KA/colors.json": "K/colors.json", "K/KA/panels.json": "K/panels.json"},
            required_kinds=("colors",),
        )
        self.assertNotIn("panels", result["default"]["K/KA"]["files"])

    def test_passing_gate_keeps_entry_in_default(self) -> None:
        gates = [{"dataset": "mva", "path": "L/*", "min_game_version": "0.6.1.0"}]
        entries = {"LEMD": _file("L/LE/LEMD/mva.json")}
        result = GATES.apply_gates("mva", entries, gates=gates, live_versions=LIVE)
        self.assertEqual(result["default"], entries)
        self.assertEqual(result["v3_entries"][0]["min_game_version"], "0.6.1.0")


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
        RELEASE_TESTS.write_json(root / "release" / "live_versions.json", LIVE_FILE)

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
                    {"dataset": "mva", "path": "L/LE/LECB/*", "min_game_version": "0.6.2.380"},
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
            self.assertEqual(lebl["min_game_version"], "0.6.2.380")

            colors = bundle["manifests"]["color_profiles"]["profiles"]
            self.assertTrue(all(set(profile["files"]) == {"colors"} for profile in colors.values()))
            with zipfile.ZipFile(bundle["assets"]["color_profiles_zip"]["path"]) as archive:
                self.assertFalse(any(name.endswith("style.json") for name in archive.namelist()))
            # Datasets without gates are untouched.
            self.assertEqual(bundle["manifests"]["runway_configs"], ungated["manifests"]["runway_configs"])

    def test_gates_need_live_versions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            RELEASE_TESTS.build_fixture_repo(root)
            RELEASE_TESTS.write_json(
                root / ".voiceatc" / "gates.json",
                {"schema_version": 1, "gates": [{"dataset": "mva", "path": "L/*", "channels": ["closed-beta"]}]},
            )
            with self.assertRaises(ValueError):
                self._bundle(root, "a")


if __name__ == "__main__":
    unittest.main()
