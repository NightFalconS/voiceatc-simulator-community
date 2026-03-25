import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "tools" / "mva_manifest.py"
SPEC = importlib.util.spec_from_file_location("mva_manifest", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def valid_payload(airport: str) -> dict[str, object]:
    return {
        "airport": airport,
        "mva_areas": [
            {
                "area_id": "AREA_1",
                "minimum_altitude_ft": 3000,
                "labels": [{"text": "3.0", "position": [41.0, 2.0]}],
                "polygon": [[41.0, 2.0], [41.1, 2.1], [41.2, 2.0]],
            }
        ],
    }


class MvaManifestTests(unittest.TestCase):
    def test_repository_contains_expected_mva_files(self) -> None:
        manifest = MODULE.build_manifest(REPO_ROOT, commit_sha="test-commit")
        expected_airports = {"EHAM", "LEBB", "LEBL", "LEMD", "LEMG", "LEPA"}
        found_airports = set(manifest["airports"].keys())
        self.assertTrue(
            expected_airports.issubset(found_airports),
            f"Missing core airports: {expected_airports - found_airports}",
        )

    def test_validate_mva_file_rejects_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "LEBL" / "mva.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{bad json", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invalid JSON"):
                MODULE.validate_mva_file(path, Path(tmp_dir))

    def test_validate_mva_file_accepts_tma_folder_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            path = root / "BARCELONA_TMA" / "mva.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(valid_payload("LEMD")), encoding="utf-8")
            entry = MODULE.validate_mva_file(path, root)
            self.assertEqual("LEMD", entry["airport"])

    def test_validate_mva_file_ignores_legacy_schema_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            path = root / "LEBL" / "mva.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = valid_payload("LEBL")
            payload["schema_version"] = "obsolete"
            path.write_text(json.dumps(payload), encoding="utf-8")
            entry = MODULE.validate_mva_file(path, root)
            self.assertEqual("LEBL", entry["airport"])

    def test_validate_mva_file_rejects_empty_area_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            path = root / "LEBL" / "mva.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = valid_payload("LEBL")
            payload["mva_areas"] = []
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "non-empty mva_areas"):
                MODULE.validate_mva_file(path, root)

    def test_validate_mva_file_rejects_short_polygon(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            path = root / "LEBL" / "mva.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = valid_payload("LEBL")
            payload["mva_areas"][0]["polygon"] = [[41.0, 2.0], [41.1, 2.1]]
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "at least 3 points"):
                MODULE.validate_mva_file(path, root)

    def test_validate_mva_file_rejects_missing_minimum_altitude(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            path = root / "LEBL" / "mva.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = valid_payload("LEBL")
            del payload["mva_areas"][0]["minimum_altitude_ft"]
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "minimum_altitude_ft"):
                MODULE.validate_mva_file(path, root)

    def test_build_manifest_rejects_duplicate_airports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            path_a = root / "A" / "LEBL" / "mva.json"
            path_b = root / "B" / "LEBL" / "mva.json"
            path_a.parent.mkdir(parents=True, exist_ok=True)
            path_b.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(valid_payload("LEBL"))
            path_a.write_text(payload, encoding="utf-8")
            path_b.write_text(payload, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate airport"):
                MODULE.build_manifest(root, commit_sha="test-commit")


if __name__ == "__main__":
    unittest.main()
