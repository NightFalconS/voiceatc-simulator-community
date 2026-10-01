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


GUARD = _load("stable_contract_guard", TOOLS_DIR / "stable_contract_guard.py")
RELEASE = _load("community_release_manifest", TOOLS_DIR / "community_release_manifest.py")
RELEASE_TESTS = _load("test_community_release_manifest", REPO_ROOT / "tests" / "test_community_release_manifest.py")


class StableContractGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        RELEASE_TESTS.build_fixture_repo(self.root)
        self.bundle = RELEASE.build_release_bundle(
            output_dir=self.root / "out",
            release_tag="daily-2026-10-01",
            published_at="2026-10-01T00:00:00Z",
            commit_sha="abc123",
            download_repo="lainoa-software/voiceatc-simulator-community",
            root=self.root,
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _errors(self, dataset: str) -> list[str]:
        manifest = self.bundle["manifests"][dataset]
        zip_path = Path(self.bundle["assets"][GUARD.ZIP_DATASETS[dataset]["asset_key"]]["path"])
        return GUARD.check_zip_dataset(dataset, manifest, zip_path)

    def test_todays_release_output_passes(self) -> None:
        for dataset in GUARD.ZIP_DATASETS:
            with self.subTest(dataset=dataset):
                self.assertEqual(self._errors(dataset), [])

    def test_unexpected_zip_entry_fails(self) -> None:
        zip_path = Path(self.bundle["assets"]["mva_zip"]["path"])
        with zipfile.ZipFile(zip_path, "a") as archive:
            archive.writestr("L/LE/panels.json", "{}")
        manifest = dict(self.bundle["manifests"]["mva"])
        raw = zip_path.read_bytes()
        manifest["sha256"] = GUARD._sha256(raw)
        manifest["size_bytes"] = len(raw)
        errors = GUARD.check_zip_dataset("mva", manifest, zip_path)
        self.assertTrue(any("not listed" in error for error in errors), errors)

    def test_new_file_kind_fails(self) -> None:
        manifest = json.loads(json.dumps(self.bundle["manifests"]["color_profiles"]))
        scope = next(iter(manifest["profiles"]))
        manifest["profiles"][scope]["files"]["panels"] = {
            "repo_path": f"{scope}/panels.json",
            "sha256": "0" * 64,
            "size_bytes": 2,
        }
        errors = GUARD.check_zip_dataset(
            "color_profiles", manifest, Path(self.bundle["assets"]["color_profiles_zip"]["path"])
        )
        self.assertTrue(any("kinds" in error for error in errors), errors)

    def test_new_top_level_or_entry_key_fails(self) -> None:
        manifest = json.loads(json.dumps(self.bundle["manifests"]["runway_configs"]))
        manifest["min_game_version"] = "0.6.2.380"
        first = next(iter(manifest["airports"]))
        manifest["airports"][first]["channels"] = ["closed-beta"]
        errors = GUARD.check_zip_dataset(
            "runway_configs", manifest, Path(self.bundle["assets"]["runway_configs_zip"]["path"])
        )
        self.assertTrue(any("top-level keys" in error for error in errors), errors)
        self.assertTrue(any("entry keys" in error for error in errors), errors)

    def test_wrong_schema_and_count_fail(self) -> None:
        manifest = json.loads(json.dumps(self.bundle["manifests"]["sector_data"]))
        manifest["schema_version"] = 3
        manifest["bundle_count"] = 99
        errors = GUARD.check_zip_dataset(
            "sector_data", manifest, Path(self.bundle["assets"]["sector_data_zip"]["path"])
        )
        self.assertTrue(any("schema_version" in error for error in errors), errors)
        self.assertTrue(any("bundle_count" in error for error in errors), errors)

    def test_visual_manifest_exact_key_rule(self) -> None:
        good = {
            "schema_version": 1,
            "repo": GUARD.REPO_NAME,
            "published_at": "2026-10-01T00:00:00Z",
            "airports": {
                "KASE": {
                    "repo_path": "K/KZDV/ASPEN_TMA/KASE/visual_procedures.json",
                    "sha256": "a" * 64,
                    "size_bytes": 10,
                }
            },
        }
        self.assertEqual(GUARD.check_file_manifest("visual_procedures", good), [])
        extra_top = {**good, "airport_count": 1}
        self.assertTrue(GUARD.check_file_manifest("visual_procedures", extra_top))
        extra_entry = json.loads(json.dumps(good))
        extra_entry["airports"]["KASE"]["min_game_version"] = "0.6.2.380"
        self.assertTrue(GUARD.check_file_manifest("visual_procedures", extra_entry))

    def test_skins_have_no_default_path(self) -> None:
        summary = {
            "assets": {"skins_full_zip": {"asset_name": "skins-full.zip"}},
            "manifests": {"release": {"assets": {"mva_zip": {}}}},
        }
        self.assertEqual(GUARD.check_no_default_skins(self.root, summary), [])
        for broken in (
            {"assets": {"skins_zip": {"asset_name": "skins-2609.zip"}}, "manifests": {"release": {"assets": {}}}},
            {"assets": {}, "manifests": {"skins": {}, "release": {"assets": {}}}},
            {"assets": {}, "manifests": {"release": {"assets": {"skins_zip": {}}}}},
            {"assets": {"extra": {"asset_name": "skins-2609.zip"}}, "manifests": {"release": {"assets": {}}}},
        ):
            with self.subTest(broken=broken):
                self.assertTrue(GUARD.check_no_default_skins(self.root, broken))

    def test_the_real_release_summary_has_no_default_skins(self) -> None:
        self.assertEqual(GUARD.check_no_default_skins(self.root, self.bundle), [])

    def test_a_committed_default_skins_manifest_fails(self) -> None:
        (self.root / ".voiceatc").mkdir(exist_ok=True)
        (self.root / ".voiceatc" / "skins_manifest.json").write_text("{}", encoding="utf-8")
        errors = GUARD.check_repo_manifests(self.root)
        self.assertTrue(any("skins_manifest.json" in error for error in errors), errors)

    def test_a_skin_in_the_default_colour_zip_fails(self) -> None:
        zip_path = Path(self.bundle["assets"]["color_profiles_zip"]["path"])
        with zipfile.ZipFile(zip_path, "a") as archive:
            archive.writestr("SKINS/harbour-blue/panels.json", "{}")
        manifest = dict(self.bundle["manifests"]["color_profiles"])
        raw = zip_path.read_bytes()
        manifest["sha256"] = GUARD._sha256(raw)
        manifest["size_bytes"] = len(raw)
        errors = GUARD.check_zip_dataset("color_profiles", manifest, zip_path)
        self.assertTrue(any("not listed" in error for error in errors), errors)

    def test_committed_per_file_manifests_pass(self) -> None:
        self.assertEqual(GUARD.check_repo_manifests(REPO_ROOT), [])


if __name__ == "__main__":
    unittest.main()
