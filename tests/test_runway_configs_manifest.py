import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "tools" / "runway_configs_manifest.py"
SPEC = importlib.util.spec_from_file_location("runway_configs_manifest", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class RunwayConfigsManifestTests(unittest.TestCase):
    def test_repository_contains_only_plural_runway_config_filenames(self) -> None:
        legacy_files = MODULE.legacy_runway_files(REPO_ROOT)
        self.assertEqual([], legacy_files, f"Legacy runway config filenames found: {legacy_files}")

    def test_build_manifest_rejects_legacy_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            legacy_file = root / "E" / "ES" / "TEST" / "TEST_APP" / "ESSB" / "runway_config.json"
            legacy_file.parent.mkdir(parents=True, exist_ok=True)
            legacy_file.write_text(
                json.dumps(
                    {
                        "airport": "ESSB",
                        "runway_configurations": [{"id": "TEST", "arr": "12", "dep": "30"}],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "legacy runway filename"):
                MODULE.build_manifest(root, commit_sha="test-commit")

    def test_build_manifest_accepts_plural_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            valid_file = root / "E" / "ES" / "TEST" / "TEST_APP" / "ESSB" / "runway_configs.json"
            valid_file.parent.mkdir(parents=True, exist_ok=True)
            valid_file.write_text(
                json.dumps(
                    {
                        "airport": "ESSB",
                        "runway_configurations": [{"id": "TEST", "arr": "12", "dep": "30"}],
                    }
                ),
                encoding="utf-8",
            )

            manifest = MODULE.build_manifest(root, commit_sha="test-commit")

            self.assertIn("ESSB", manifest["airports"])
            self.assertEqual(
                "E/ES/TEST/TEST_APP/ESSB/runway_configs.json",
                manifest["airports"]["ESSB"]["repo_path"],
            )


if __name__ == "__main__":
    unittest.main()
