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


MODULE = _load("skins_manifest", TOOLS_DIR / "skins_manifest.py")
RELEASE = _load("community_release_manifest", TOOLS_DIR / "community_release_manifest.py")
RELEASE_TESTS = _load("test_community_release_manifest", REPO_ROOT / "tests" / "test_community_release_manifest.py")


def valid_skin(**overrides: object) -> dict[str, object]:
    skin: dict[str, object] = {
        "name": "Harbour Blue",
        "author": "Jane Modder",
        "description": "Cool blue bars with bevelled cells.",
        "tokens": {
            "colors": {"bar": "1F3555"},
            "fonts": {"text": "barlow_semi_condensed"},
            "case": "upper",
            "bevel": {"width": 2},
        },
    }
    skin.update(overrides)
    return skin


def write_skin(root: Path, skin_id: str, payload: object, *, raw: str | None = None) -> Path:
    path = root / "SKINS" / skin_id / "panels.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(raw if raw is not None else json.dumps(payload), encoding="utf-8")
    return path


class SkinsManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def build(self) -> dict[str, object]:
        return MODULE.build_manifest(self.root, commit_sha="test-commit")

    def test_no_catalog_is_an_empty_manifest(self) -> None:
        manifest = self.build()
        self.assertEqual({}, manifest["skins"])
        self.assertNotIn("schema_version", manifest)

    def test_accepts_a_skin_and_lists_its_metadata_and_hash(self) -> None:
        path = write_skin(self.root, "harbour-blue", valid_skin())
        entry = self.build()["skins"]["harbour-blue"]
        self.assertEqual("SKINS/harbour-blue/panels.json", entry["repo_path"])
        self.assertEqual("Harbour Blue", entry["name"])
        self.assertEqual("Jane Modder", entry["author"])
        self.assertEqual("Cool blue bars with bevelled cells.", entry["description"])
        self.assertEqual(path.stat().st_size, entry["size_bytes"])
        self.assertEqual(64, len(entry["sha256"]))

    def test_description_is_optional(self) -> None:
        skin = valid_skin()
        del skin["description"]
        write_skin(self.root, "plain", skin)
        self.assertNotIn("description", self.build()["skins"]["plain"])

    def test_name_and_author_are_required(self) -> None:
        for missing in ("name", "author"):
            with self.subTest(missing=missing):
                skin = valid_skin()
                del skin[missing]
                write_skin(self.root, "no-meta", skin)
                with self.assertRaisesRegex(ValueError, f"'{missing}'"):
                    self.build()

    def test_metadata_limits_and_shape(self) -> None:
        bad = [
            {"name": ""},
            {"name": "   "},
            {"name": " padded"},
            {"name": "x" * 41},
            {"name": "two\nlines"},
            {"name": 7},
            {"author": "y" * 61},
            {"description": "z" * 201},
            {"description": ""},
        ]
        for override in bad:
            with self.subTest(override=override):
                write_skin(self.root, "bad-meta", valid_skin(**override))
                with self.assertRaises(ValueError):
                    self.build()

    def test_same_key_rules_as_panels_json(self) -> None:
        bad = [
            {"unknown_key": "x"},
            {"tokens": {"colors": {"bar": "#1F3555"}}},
            {"tokens": {"bevel": {"width": 9}}},
            {"bar_style": "cells"},
            {"tokens": {"fonts": {"text": "comic_sans"}}},
            {"components": {"menus": {"mode": "dock_strip"}}},
            {"extends": "skin:not-here"},
        ]
        for override in bad:
            with self.subTest(override=override):
                write_skin(self.root, "bad-key", valid_skin(**override))
                with self.assertRaises(ValueError):
                    self.build()

    def test_skin_ids_are_lowercase_slugs_and_not_reserved(self) -> None:
        for skin_id in ("Harbour", "har bour", "-lead", "trail-", "dou--ble", "x" * 41, "generic", "realistic"):
            with self.subTest(skin_id=skin_id):
                write_skin(self.root, skin_id, valid_skin())
                with self.assertRaisesRegex(ValueError, "skin id"):
                    self.build()
                (self.root / "SKINS" / skin_id / "panels.json").unlink()
                (self.root / "SKINS" / skin_id).rmdir()

    def test_folder_must_hold_panels_json_and_only_a_readme_beside_it(self) -> None:
        (self.root / "SKINS" / "empty").mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "panels.json"):
            self.build()
        write_skin(self.root, "empty", valid_skin())
        (self.root / "SKINS" / "empty" / "README.md").write_text("About this skin.\n", encoding="utf-8")
        self.assertIn("empty", self.build()["skins"])
        (self.root / "SKINS" / "empty" / "font.ttf").write_bytes(b"x")
        with self.assertRaisesRegex(ValueError, "font.ttf"):
            self.build()

    def test_stray_files_in_the_catalog_root_are_rejected(self) -> None:
        write_skin(self.root, "ok", valid_skin())
        (self.root / "SKINS" / "README.md").write_text("Catalog.\n", encoding="utf-8")
        self.assertIn("ok", self.build()["skins"])
        (self.root / "SKINS" / "notes.txt").write_text("x", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "notes.txt"):
            self.build()

    def test_names_are_unique_ignoring_case(self) -> None:
        write_skin(self.root, "one", valid_skin(name="Harbour Blue"))
        write_skin(self.root, "two", valid_skin(name="harbour blue"))
        with self.assertRaisesRegex(ValueError, "already used"):
            self.build()

    def test_rejects_empty_non_object_invalid_json_and_oversize(self) -> None:
        for raw in ("{}", "[1]", "{not json"):
            with self.subTest(raw=raw):
                write_skin(self.root, "broken", None, raw=raw)
                with self.assertRaises(ValueError):
                    self.build()
        padded = json.dumps(valid_skin()) + " " * (MODULE.MAX_SKIN_BYTES + 1)
        write_skin(self.root, "broken", None, raw=padded)
        with self.assertRaisesRegex(ValueError, "bytes"):
            self.build()

    def test_repository_catalog_is_valid(self) -> None:
        manifest = MODULE.build_manifest(REPO_ROOT, commit_sha="test-commit")
        for skin_id, entry in manifest["skins"].items():
            self.assertEqual(f"SKINS/{skin_id}/panels.json", entry["repo_path"])

    def test_there_is_no_default_manifest_to_write(self) -> None:
        self.assertFalse(hasattr(MODULE, "MANIFEST_PATH"))


class SkinsReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        RELEASE_TESTS.build_fixture_repo(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def bundle(self, out: str = "out") -> dict[str, object]:
        return RELEASE.build_release_bundle(
            output_dir=self.root / out,
            release_tag="daily-2026-10-01",
            published_at="2026-10-01T00:00:00Z",
            commit_sha="abc123",
            download_repo="lainoa-software/voiceatc-simulator-community",
            root=self.root,
        )

    def test_skins_ship_only_in_the_full_feed_with_a_full_zip(self) -> None:
        write_skin(self.root, "harbour-blue", valid_skin())
        write_skin(self.root, "amber", valid_skin(name="Amber Night", author="Sam"))
        bundle = self.bundle()

        full = bundle["full_manifests"]["skins"]
        self.assertNotIn("schema_version", full)
        self.assertEqual(
            self.root / ".voiceatc" / "full" / "skins_manifest.json",
            RELEASE.release_gates.full_manifest_path("skins", self.root),
        )
        self.assertEqual("skins", full["dataset"])
        self.assertEqual("skins-full.zip", full["asset_name"])
        self.assertEqual(
            "https://github.com/lainoa-software/voiceatc-simulator-community/releases/download/daily-2026-10-01/skins-full.zip",
            full["download_url"],
        )
        self.assertEqual(2, full["entry_count"])
        self.assertEqual(["amber", "harbour-blue"], sorted(entry["id"] for entry in full["entries"]))
        entry = next(item for item in full["entries"] if item["id"] == "harbour-blue")
        self.assertEqual("Harbour Blue", entry["name"])
        self.assertEqual("SKINS/harbour-blue/panels.json", entry["repo_path"])
        self.assertEqual(bundle["assets"]["skins_full_zip"]["sha256"], full["sha256"])
        with zipfile.ZipFile(bundle["assets"]["skins_full_zip"]["path"]) as archive:
            self.assertEqual(
                ["SKINS/amber/panels.json", "SKINS/harbour-blue/panels.json"], sorted(archive.namelist())
            )

        # Nothing for old builds: no default manifest, no default zip, no release-manifest asset.
        self.assertNotIn("skins", bundle["manifests"])
        self.assertNotIn("skins_zip", bundle["assets"])
        self.assertFalse(any("skins" in key for key in bundle["manifests"]["release"]["assets"]))
        produced = {path.name for path in (self.root / "out").iterdir()}
        self.assertEqual({"skins-full.zip"}, {name for name in produced if name.startswith("skins")})

    def test_skins_never_reach_the_colour_profile_feed(self) -> None:
        write_skin(self.root, "harbour-blue", valid_skin())
        bundle = self.bundle()
        profiles = bundle["manifests"]["color_profiles"]["profiles"]
        self.assertFalse(any(scope.startswith("SKINS") for scope in profiles))
        with zipfile.ZipFile(bundle["assets"]["color_profiles_zip"]["path"]) as archive:
            self.assertFalse(any(name.startswith("SKINS/") for name in archive.namelist()))

    def test_default_feed_is_identical_with_and_without_skins(self) -> None:
        before = self.bundle("a")
        write_skin(self.root, "harbour-blue", valid_skin())
        after = self.bundle("b")
        self.assertEqual(before["manifests"], after["manifests"])
        for key in ("mva_zip", "runway_configs_zip", "sector_data_zip", "misc_drawings_zip", "color_profiles_zip"):
            self.assertEqual(
                Path(before["assets"][key]["path"]).read_bytes(), Path(after["assets"][key]["path"]).read_bytes()
            )

    def test_an_empty_catalog_still_writes_an_empty_full_manifest(self) -> None:
        full = self.bundle()["full_manifests"]["skins"]
        self.assertEqual(0, full["entry_count"])
        self.assertEqual([], full["entries"])

    def test_skins_can_be_gated_and_the_gate_reaches_the_full_feed(self) -> None:
        write_skin(self.root, "harbour-blue", valid_skin())
        RELEASE_TESTS.write_json(
            self.root / ".voiceatc" / "gates.json",
            {"gates": [{"dataset": "skins", "path": "SKINS/*", "requires": ["skins.catalog"]}]},
        )
        entry = self.bundle()["full_manifests"]["skins"]["entries"][0]
        self.assertEqual(["skins.catalog"], entry["requires"])

    def test_the_committed_gates_require_the_capability_that_reads_each_content(self) -> None:
        gates = json.loads((REPO_ROOT / ".voiceatc" / "gates.json").read_text(encoding="utf-8"))["gates"]
        panels = next(gate for gate in gates if gate.get("kind") == "panels")
        skins = next(gate for gate in gates if gate.get("dataset") == "skins")
        self.assertEqual({"dataset": "color_profiles", "kind": "panels", "requires": ["color_profiles.panels"]}, panels)
        self.assertEqual({"dataset": "skins", "path": "SKINS/*", "requires": ["skins.catalog"]}, skins)


if __name__ == "__main__":
    unittest.main()
