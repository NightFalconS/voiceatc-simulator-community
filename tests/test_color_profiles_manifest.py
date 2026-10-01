import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "tools" / "color_profiles_manifest.py"
SPEC = importlib.util.spec_from_file_location("color_profiles_manifest", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def valid_colors() -> dict[str, object]:
    return {
        "assumed_tfc_color": "3bf451",
        "bg_color": "080808",
    }


def valid_style() -> dict[str, object]:
    return {
        "symbol_size": 0.6,
        "traildot_size": 0.15,
        "symbol_line_width": 2.0,
        "defined_symbols": {
            "diamond": {
                "type": "wireframe",
                "draw": "M 0 -7 L 7 0 L 0 7 L -7 0 L 0 -7",
                "connection_points": [[0, -7], [7, 0], [0, 7], [-7, 0]],
            },
        },
        "assumed_symbol": "diamond",
    }


def valid_panels() -> dict[str, object]:
    return {
        "frame_style": "sacta",
        "bar_style": "cells",
        "strip_style": "paper_es",
        "text_case": "upper",
        "bevel": 2,
        "bar_color": "1F2535",
        "edge_color": "394258cc",
        "text_font": "barlow_semi_condensed",
        "data_font": "pixel_mono",
    }


def legacy_us_aliases() -> list[str]:
    return [f"K/K{chr(letter)}" for letter in range(ord("A"), ord("Z") + 1)]


def write_compatibility_registry(root: Path, aliases: dict[str, list[str]] | None = None) -> None:
    path = root / "documentation" / "content_hierarchy.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "nationality_areas": {"K": []},
                "release_compatibility": {
                    "color_profile_aliases": aliases or {},
                    "retention": "until_explicit_deprecation",
                }
            }
        ),
        encoding="utf-8",
    )


class ColorProfilesManifestTests(unittest.TestCase):
    def test_repository_contains_expected_scope_paths(self) -> None:
        manifest = MODULE.build_manifest(REPO_ROOT, commit_sha="test-commit")
        core_scopes = {"E/EH", "G/GC", "L/LE"}
        found_scopes = set(manifest["profiles"].keys())
        self.assertTrue(core_scopes.issubset(found_scopes), f"Missing core scopes: {core_scopes - found_scopes}")

    def test_repository_release_projection_matches_legacy_contract(self) -> None:
        canonical = MODULE.build_manifest(REPO_ROOT, commit_sha="test-commit")
        projection = MODULE.build_release_projection(REPO_ROOT, commit_sha="test-commit")
        aliases = set(legacy_us_aliases())

        canonical_scopes = set(canonical["profiles"])
        projection_scopes = set(projection["profiles"])

        # The single-segment K region scope is replaced by its 26 US aliases;
        # every multi-segment canonical scope passes through unchanged.
        self.assertNotIn("K", projection_scopes)
        self.assertEqual(canonical_scopes - {"K"}, projection_scopes - aliases)
        self.assertEqual(aliases, {scope for scope in projection_scopes if scope.startswith("K/")})

        # Archive sources cover every released file exactly once, mapping each alias
        # back to the canonical K source and leaving pass-through paths untouched.
        expected_archive_paths = {
            entry["repo_path"]
            for profile in projection["profiles"].values()
            for entry in profile["files"].values()
        }
        self.assertEqual(expected_archive_paths, set(projection["archive_sources"]))
        for scope, profile in projection["profiles"].items():
            for kind, entry in profile["files"].items():
                file_name = MODULE.PROFILE_FILE_NAMES[kind]
                self.assertEqual(f"{scope}/{file_name}", entry["repo_path"])
                if scope in aliases:
                    self.assertEqual(f"K/{file_name}", projection["archive_sources"][entry["repo_path"]])
                else:
                    self.assertEqual(entry["repo_path"], projection["archive_sources"][entry["repo_path"]])

    def test_build_manifest_accepts_region_country_fir_acc_tma_scopes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            for parts in [
                ("K",),
                ("L", "LE"),
                ("L", "LE", "LECM"),
                ("L", "LE", "LECM", "LECM_R2"),
                ("L", "LE", "LECM", "LECM_R2", "MADRID_TMA"),
            ]:
                scope_dir = root.joinpath(*parts)
                scope_dir.mkdir(parents=True, exist_ok=True)
                (scope_dir / "colors.json").write_text(json.dumps(valid_colors()), encoding="utf-8")
                (scope_dir / "style.json").write_text(json.dumps(valid_style()), encoding="utf-8")

            manifest = MODULE.build_manifest(root, commit_sha="test-commit")
            self.assertEqual(
                {
                    "K",
                    "L/LE",
                    "L/LE/LECM",
                    "L/LE/LECM/LECM_R2",
                    "L/LE/LECM/LECM_R2/MADRID_TMA",
                },
                set(manifest["profiles"].keys()),
            )

    def test_build_manifest_accepts_colors_only_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            scope_dir = root / "L" / "LE"
            scope_dir.mkdir(parents=True, exist_ok=True)
            (scope_dir / "colors.json").write_text(json.dumps(valid_colors()), encoding="utf-8")
            manifest = MODULE.build_manifest(root, commit_sha="test-commit")
            self.assertIn("L/LE", manifest["profiles"])
            self.assertNotIn("style", manifest["profiles"]["L/LE"]["files"])

    def test_release_projection_replaces_region_scope_with_exact_legacy_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            scope_dir = root / "K"
            scope_dir.mkdir(parents=True)
            (scope_dir / "colors.json").write_text(json.dumps(valid_colors()), encoding="utf-8")
            (scope_dir / "style.json").write_text(json.dumps(valid_style()), encoding="utf-8")
            aliases = legacy_us_aliases()
            write_compatibility_registry(root, {"K": aliases})

            canonical = MODULE.build_manifest(root, commit_sha="test-commit")
            projection = MODULE.build_release_projection(root, commit_sha="test-commit")

            self.assertEqual({"K"}, set(canonical["profiles"]))
            self.assertNotIn("K", projection["profiles"])
            self.assertEqual(set(aliases), set(projection["profiles"]))
            for alias in aliases:
                for kind in canonical["profiles"]["K"]["files"]:
                    file_name = MODULE.PROFILE_FILE_NAMES[kind]
                    public_entry = projection["profiles"][alias]["files"][kind]
                    source_entry = canonical["profiles"]["K"]["files"][kind]
                    self.assertEqual(source_entry["sha256"], public_entry["sha256"])
                    self.assertEqual(source_entry["size_bytes"], public_entry["size_bytes"])
                    archive_path = f"{alias}/{file_name}"
                    self.assertEqual(archive_path, public_entry["repo_path"])
                    self.assertEqual(f"K/{file_name}", projection["archive_sources"][archive_path])

    def test_release_projection_preserves_optional_style(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            scope_dir = root / "K"
            scope_dir.mkdir(parents=True)
            (scope_dir / "colors.json").write_text(json.dumps(valid_colors()), encoding="utf-8")
            write_compatibility_registry(root, {"K": legacy_us_aliases()})

            projection = MODULE.build_release_projection(root, commit_sha="test-commit")

            self.assertTrue(all(set(profile["files"]) == {"colors"} for profile in projection["profiles"].values()))
            self.assertEqual(26, len(projection["archive_sources"]))

    def test_release_projection_rejects_undeclared_region_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            scope_dir = root / "K"
            scope_dir.mkdir(parents=True)
            (scope_dir / "colors.json").write_text(json.dumps(valid_colors()), encoding="utf-8")
            write_compatibility_registry(root)

            with self.assertRaisesRegex(ValueError, "requires declared legacy release aliases"):
                MODULE.build_release_projection(root, commit_sha="test-commit")

    def test_release_projection_rejects_alias_source_collision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "K").mkdir(parents=True)
            (root / "K" / "colors.json").write_text(json.dumps(valid_colors()), encoding="utf-8")
            alias_dir = root / "K" / "KA"
            alias_dir.mkdir(parents=True)
            (alias_dir / "colors.json").write_text(json.dumps(valid_colors()), encoding="utf-8")
            write_compatibility_registry(root, {"K": legacy_us_aliases()})

            with self.assertRaisesRegex(ValueError, "collides with source scope"):
                MODULE.build_release_projection(root, commit_sha="test-commit")

    def test_release_projection_rejects_missing_canonical_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_compatibility_registry(root, {"K": legacy_us_aliases()})

            with self.assertRaisesRegex(ValueError, "missing source scopes"):
                MODULE.build_release_projection(root, commit_sha="test-commit")

    def test_release_projection_rejects_aliases_for_unregistered_region(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            scope_dir = root / "X"
            scope_dir.mkdir(parents=True)
            (scope_dir / "colors.json").write_text(json.dumps(valid_colors()), encoding="utf-8")
            write_compatibility_registry(root, {"X": ["X/XA"]})

            with self.assertRaisesRegex(ValueError, "registered region scope"):
                MODULE.build_release_projection(root, commit_sha="test-commit")

    def test_build_manifest_rejects_missing_colors_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            scope_dir = root / "L" / "LE"
            scope_dir.mkdir(parents=True, exist_ok=True)
            (scope_dir / "style.json").write_text(json.dumps(valid_style()), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing color profile files: colors"):
                MODULE.build_manifest(root, commit_sha="test-commit")

    def test_validate_colors_rejects_invalid_hex(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            scope_dir = root / "L" / "LE"
            scope_dir.mkdir(parents=True, exist_ok=True)
            bad_colors = valid_colors()
            bad_colors["assumed_tfc_color"] = "not-a-color"
            (scope_dir / "colors.json").write_text(json.dumps(bad_colors), encoding="utf-8")
            (scope_dir / "style.json").write_text(json.dumps(valid_style()), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hex color"):
                MODULE.build_manifest(root, commit_sha="test-commit")

    def test_validate_style_rejects_invalid_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            scope_dir = root / "L" / "LE"
            scope_dir.mkdir(parents=True, exist_ok=True)
            bad_style = valid_style()
            bad_style["bg_color"] = "080808"
            (scope_dir / "colors.json").write_text(json.dumps(valid_colors()), encoding="utf-8")
            (scope_dir / "style.json").write_text(json.dumps(bad_style), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "style.json only accepts"):
                MODULE.build_manifest(root, commit_sha="test-commit")

    def test_validate_style_accepts_numeric_config_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            scope_dir = root / "L" / "LE"
            scope_dir.mkdir(parents=True, exist_ok=True)
            style = valid_style()
            style["symbol_size"] = 0.8
            style["traildot_size"] = 0.2
            style["symbol_line_width"] = 3.0
            (scope_dir / "colors.json").write_text(json.dumps(valid_colors()), encoding="utf-8")
            (scope_dir / "style.json").write_text(json.dumps(style), encoding="utf-8")
            manifest = MODULE.build_manifest(root, commit_sha="test-commit")
            self.assertIn("L/LE", manifest["profiles"])

    def test_validate_style_accepts_objective_symbol_height(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            scope_dir = root / "L" / "LE"
            scope_dir.mkdir(parents=True, exist_ok=True)
            style = valid_style()
            style["defined_symbols"]["diamond"]["height"] = 0.78
            (scope_dir / "colors.json").write_text(json.dumps(valid_colors()), encoding="utf-8")
            (scope_dir / "style.json").write_text(json.dumps(style), encoding="utf-8")
            manifest = MODULE.build_manifest(root, commit_sha="test-commit")
            self.assertIn("L/LE", manifest["profiles"])

    def test_validate_style_rejects_invalid_objective_symbol_height(self) -> None:
        invalid_heights = [0, -0.1, True, "0.78", float("nan"), float("inf")]
        for invalid_height in invalid_heights:
            with self.subTest(height=invalid_height), tempfile.TemporaryDirectory() as tmp_dir:
                root = Path(tmp_dir)
                scope_dir = root / "L" / "LE"
                scope_dir.mkdir(parents=True, exist_ok=True)
                style = valid_style()
                style["defined_symbols"]["diamond"]["height"] = invalid_height
                (scope_dir / "colors.json").write_text(json.dumps(valid_colors()), encoding="utf-8")
                (scope_dir / "style.json").write_text(json.dumps(style), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "height.*finite positive number"):
                    MODULE.build_manifest(root, commit_sha="test-commit")

    def test_validate_style_accepts_label_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            scope_dir = root / "L" / "LE"
            scope_dir.mkdir(parents=True, exist_ok=True)
            style = valid_style()
            style["label"] = {
                "row_count": 2,
                "col_count": 1,
                "fields": [{"id": "CS", "row": 0, "col": 0, "content_source": "flight.cs"}],
            }
            (scope_dir / "colors.json").write_text(json.dumps(valid_colors()), encoding="utf-8")
            (scope_dir / "style.json").write_text(json.dumps(style), encoding="utf-8")
            manifest = MODULE.build_manifest(root, commit_sha="test-commit")
            self.assertIn("L/LE", manifest["profiles"])

    def test_validate_style_rejects_non_object_label_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            scope_dir = root / "L" / "LE"
            scope_dir.mkdir(parents=True, exist_ok=True)
            bad_style = valid_style()
            bad_style["label"] = "full"
            (scope_dir / "colors.json").write_text(json.dumps(valid_colors()), encoding="utf-8")
            (scope_dir / "style.json").write_text(json.dumps(bad_style), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "'label' must be a non-empty object"):
                MODULE.build_manifest(root, commit_sha="test-commit")

    def test_validate_style_rejects_invalid_symbol_definition(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            scope_dir = root / "L" / "LE"
            scope_dir.mkdir(parents=True, exist_ok=True)
            bad_style = valid_style()
            bad_style["defined_symbols"]["diamond"] = 12345
            (scope_dir / "colors.json").write_text(json.dumps(valid_colors()), encoding="utf-8")
            (scope_dir / "style.json").write_text(json.dumps(bad_style), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must be an object"):
                MODULE.build_manifest(root, commit_sha="test-commit")

    def test_validate_style_rejects_symbol_missing_required_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            scope_dir = root / "L" / "LE"
            scope_dir.mkdir(parents=True, exist_ok=True)
            bad_style = valid_style()
            bad_style["defined_symbols"]["diamond"] = {"type": "wireframe", "draw": "M 0 0"}
            (scope_dir / "colors.json").write_text(json.dumps(valid_colors()), encoding="utf-8")
            (scope_dir / "style.json").write_text(json.dumps(bad_style), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing required key"):
                MODULE.build_manifest(root, commit_sha="test-commit")

    def test_validate_style_rejects_legacy_bitmap_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            scope_dir = root / "L" / "LE"
            scope_dir.mkdir(parents=True, exist_ok=True)
            legacy_style = {
                "defined_symbols": {"diamond": "101;010;101"},
                "assumed_symbol": "diamond",
            }
            (scope_dir / "colors.json").write_text(json.dumps(valid_colors()), encoding="utf-8")
            (scope_dir / "style.json").write_text(json.dumps(legacy_style), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "legacy bitmap format"):
                MODULE.build_manifest(root, commit_sha="test-commit")


class PanelsFileTests(unittest.TestCase):
    def build(self, panels: object, *, with_colors: bool = True, raw: str | None = None) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            scope_dir = root / "L" / "LE"
            scope_dir.mkdir(parents=True, exist_ok=True)
            if with_colors:
                (scope_dir / "colors.json").write_text(json.dumps(valid_colors()), encoding="utf-8")
            text = raw if raw is not None else json.dumps(panels)
            (scope_dir / "panels.json").write_text(text, encoding="utf-8")
            return MODULE.build_manifest(root, commit_sha="test-commit")

    def test_panels_kind_is_registered(self) -> None:
        self.assertEqual("panels.json", MODULE.PROFILE_FILE_NAMES["panels"])
        self.assertEqual(("colors", "style", "panels"), MODULE.FILE_KIND_ORDER)

    def test_accepts_a_valid_panels_file_and_lists_it_in_the_manifest(self) -> None:
        manifest = self.build(valid_panels())
        entry = manifest["profiles"]["L/LE"]["files"]["panels"]
        self.assertEqual("L/LE/panels.json", entry["repo_path"])
        self.assertEqual(64, len(entry["sha256"]))
        self.assertGreater(entry["size_bytes"], 0)

    def test_accepts_a_partial_panels_file(self) -> None:
        self.assertIn("panels", self.build({"bar_color": "102030"})["profiles"]["L/LE"]["files"])

    def test_accepts_every_documented_value(self) -> None:
        for key, values in MODULE.PANELS_ENUM_VALUES.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    self.build({key: value})
        for font in ("noto_sans", "courier_prime", "barlow_semi_condensed", "pixel_mono"):
            with self.subTest(font=font):
                self.build({"text_font": font})
        for bevel in (0, 8):
            with self.subTest(bevel=bevel):
                self.build({"bevel": bevel})

    def test_rejects_an_empty_panels_file(self) -> None:
        with self.assertRaisesRegex(ValueError, "panels.json must not be empty"):
            self.build({})

    def test_rejects_non_object_and_invalid_json(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be a JSON object"):
            self.build(["bar_color"])
        with self.assertRaisesRegex(ValueError, "invalid JSON"):
            self.build(None, raw="{not json")

    def test_rejects_an_unknown_key_and_says_a_skin_cannot_add_features(self) -> None:
        for key in ("show_radar", "bar_colour", "label", "defined_symbols", "extra_font_size"):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "cannot add features"):
                self.build({key: "x"})

    def test_rejects_a_key_that_only_ends_like_a_known_one(self) -> None:
        # Unlike colors.json, any "*_color" key is not accepted: the key set is fixed.
        with self.assertRaisesRegex(ValueError, "'assumed_tfc_color'.*cannot add features"):
            self.build({"assumed_tfc_color": "3bf451"})

    def test_rejects_invalid_enum_values(self) -> None:
        bad = {
            "frame_style": "tabs",
            "bar_style": "Bars",
            "strip_style": "paper",
            "text_case": "lower",
        }
        for key, value in bad.items():
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, f"'{key}' must be one of"):
                self.build({key: value})
        with self.assertRaisesRegex(ValueError, "'frame_style' must be one of"):
            self.build({"frame_style": 1})

    def test_rejects_invalid_bevel(self) -> None:
        for bevel in (-1, 9, 1.5, 2.0, True, "2", None):
            with self.subTest(bevel=bevel), self.assertRaisesRegex(ValueError, "'bevel' must be a whole number from 0 to 8"):
                self.build({"bevel": bevel})

    def test_rejects_invalid_colours(self) -> None:
        for value in ("#1F2535", "1F253", "1F25355", "1F2535AAB", "GG2535", " 1F2535", "1F2535 ", "", 123456, None):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "'bar_color' must be RRGGBB or RRGGBBAA hex"):
                self.build({"bar_color": value})

    def test_rejects_invalid_fonts(self) -> None:
        for value in ("Noto Sans", "arial", "", 3, None):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "'text_font' must be one of"):
                self.build({"text_font": value})

    def test_rejects_panels_without_colors(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing color profile files: colors"):
            self.build(valid_panels(), with_colors=False)

    def test_panels_is_optional_beside_colors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "L" / "LE").mkdir(parents=True)
            (root / "L" / "LE" / "colors.json").write_text(json.dumps(valid_colors()), encoding="utf-8")
            manifest = MODULE.build_manifest(root, commit_sha="test-commit")
            self.assertEqual({"colors"}, set(manifest["profiles"]["L/LE"]["files"]))

    def test_release_projection_ships_panels_and_copies_it_to_the_us_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            for scope in (Path("K"), Path("L") / "LE"):
                (root / scope).mkdir(parents=True)
                (root / scope / "colors.json").write_text(json.dumps(valid_colors()), encoding="utf-8")
                (root / scope / "panels.json").write_text(json.dumps(valid_panels()), encoding="utf-8")
            write_compatibility_registry(root, {"K": legacy_us_aliases()})

            projection = MODULE.build_release_projection(root, commit_sha="test-commit")

            self.assertEqual({"colors", "panels"}, set(projection["profiles"]["L/LE"]["files"]))
            self.assertEqual("L/LE/panels.json", projection["archive_sources"]["L/LE/panels.json"])
            self.assertEqual("K/panels.json", projection["archive_sources"]["K/KA/panels.json"])
            self.assertEqual("K/panels.json", projection["archive_sources"]["K/KZ/panels.json"])
            self.assertEqual(
                projection["profiles"]["L/LE"]["files"]["panels"]["sha256"],
                MODULE.build_manifest(root, commit_sha="x")["profiles"]["L/LE"]["files"]["panels"]["sha256"],
            )

    def test_repository_panels_files_sit_beside_colors(self) -> None:
        manifest = MODULE.build_manifest(REPO_ROOT, commit_sha="test-commit")
        for scope, profile in manifest["profiles"].items():
            if "panels" in profile["files"]:
                self.assertIn("colors", profile["files"], scope)


if __name__ == "__main__":
    unittest.main()
