import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "tools" / "misc_drawings_manifest.py"
SPEC = importlib.util.spec_from_file_location("misc_drawings_manifest", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def valid_payload(airports: object = None) -> dict[str, object]:
    return {
        "airports": ["LEMD"] if airports is None else airports,
        "runway_config": "NORTH",
        "line_sections": [
            {
                "color": "STAR",
                "dash_length": 1.0,
                "gap_length": 0.0,
                "points": [[40.4, -3.7], [40.5, -3.6]],
            }
        ],
        "filled_polygons": [],
        "labels": [{"text": "TEST", "lat": 40.45, "lon": -3.65}],
    }


class MiscDrawingsManifestTests(unittest.TestCase):
    def test_repository_contains_expected_misc_drawings_files(self) -> None:
        manifest = MODULE.build_manifest(REPO_ROOT, commit_sha="test-commit")
        expected_airports = {"LEMD"}
        found_airports = set(manifest["airports"].keys())
        self.assertTrue(
            expected_airports.issubset(found_airports),
            f"Missing core airports: {expected_airports - found_airports}",
        )

    def test_validate_misc_drawings_rejects_missing_airport_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            path = root / "L" / "LE" / "LECM" / "LECM_R2" / "MADRID_TMA" / "misc_drawings.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = valid_payload()
            del payload["airports"]
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing 'airport' or 'airports' metadata"):
                MODULE.validate_misc_drawings_file(path, root)

    def test_build_manifest_rejects_duplicate_airports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            path_a = root / "A" / "misc_drawings.json"
            path_b = root / "B" / "misc_drawings.json"
            path_a.parent.mkdir(parents=True, exist_ok=True)
            path_b.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(valid_payload(["LEMD"]))
            path_a.write_text(payload, encoding="utf-8")
            path_b.write_text(payload, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate airport"):
                MODULE.build_manifest(root, commit_sha="test-commit")

    def test_build_manifest_supports_shared_files_for_multiple_airports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            path = root / "L" / "LE" / "LECM" / "LECM_R2" / "MADRID_TMA" / "misc_drawings.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(valid_payload(["LEMD", "LETO"])), encoding="utf-8")

            manifest = MODULE.build_manifest(root, commit_sha="test-commit")

            self.assertEqual({"LEMD", "LETO"}, set(manifest["airports"].keys()))
            self.assertEqual(
                "L/LE/LECM/LECM_R2/MADRID_TMA/misc_drawings.json",
                manifest["airports"]["LEMD"]["repo_path"],
            )
            self.assertEqual(
                manifest["airports"]["LEMD"]["repo_path"],
                manifest["airports"]["LETO"]["repo_path"],
            )


if __name__ == "__main__":
    unittest.main()
