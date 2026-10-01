#!/usr/bin/env python3
"""The community skins catalog: ``SKINS/<id>/panels.json`` (plus an optional README.md).

A catalog skin is a ``panels.json`` that is not tied to a place: the player picks it
from the Skin section instead of getting it by airport. It follows the same key rules
as a regional ``panels.json`` (``color_profiles_manifest.validate_panels_file``), plus
a required ``name`` and ``author``.

The catalog is published **only** in the full feed (``.voiceatc/full/skins_manifest.json``
and ``skins-full.zip``), written by ``community_release_manifest.py``. There is no
default manifest and no default zip, so builds that predate skins never read it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import color_profiles_manifest


ROOT = Path(__file__).resolve().parent.parent
REPO_NAME = "lainoa-software/voiceatc-simulator-community"
BRANCH_NAME = "main"
SKINS_DIR_NAME = color_profiles_manifest.SKINS_DIR_NAME
SKIN_FILE_NAME = "panels.json"
README_FILE_NAME = "README.md"
REQUIRED_META = ("name", "author")
SKIN_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_SKIN_ID_LENGTH = 40
# The game offers these two without the catalog ("generic" is bundled, "realistic" is
# the default choice), so a catalog skin may not take their names.
RESERVED_SKIN_IDS = ("generic", "realistic")
# A skin is a few dozen short keys; anything larger is not a skin.
MAX_SKIN_BYTES = 16 * 1024


def current_commit_sha(root: Path = ROOT) -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()


def _validate_skin_id(skin_id: str, where: Path) -> None:
    if (
        not SKIN_ID_RE.fullmatch(skin_id)
        or len(skin_id) > MAX_SKIN_ID_LENGTH
        or skin_id in RESERVED_SKIN_IDS
    ):
        raise ValueError(
            f"{where}: skin id '{skin_id}' must be a lowercase slug of letters, digits and single "
            f"hyphens, at most {MAX_SKIN_ID_LENGTH} characters, and not "
            f"{' or '.join(repr(item) for item in RESERVED_SKIN_IDS)}"
        )


def _validate_catalog_root(skins_root: Path) -> None:
    for child in sorted(skins_root.iterdir()):
        if child.is_dir():
            continue
        if child.name != README_FILE_NAME:
            raise ValueError(
                f"{child}: only skin folders and a {README_FILE_NAME} belong in {SKINS_DIR_NAME}/"
            )


def _validate_skin_folder(folder: Path) -> None:
    _validate_skin_id(folder.name, folder)
    names = sorted(child.name for child in folder.iterdir())
    if SKIN_FILE_NAME not in names:
        raise ValueError(f"{folder}: a skin folder must contain {SKIN_FILE_NAME}")
    for name in names:
        child = folder / name
        if not child.is_file() or name not in (SKIN_FILE_NAME, README_FILE_NAME):
            raise ValueError(
                f"{child}: a skin folder holds only {SKIN_FILE_NAME} and an optional {README_FILE_NAME}; "
                f"remove '{name}' (a skin cannot ship its own fonts, images or other files)"
            )


def validate_skin_file(path: Path, root: Path = ROOT) -> dict[str, object]:
    raw_size = path.stat().st_size
    if raw_size > MAX_SKIN_BYTES:
        raise ValueError(f"{path}: a skin may be at most {MAX_SKIN_BYTES} bytes, this one is {raw_size}")
    entry = dict(
        color_profiles_manifest.validate_panels_file(path, root, required_meta=REQUIRED_META)
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    for key in color_profiles_manifest.PANELS_META_KEYS:
        if key in payload:
            entry[key] = payload[key]
    return entry


def build_manifest(root: Path = ROOT, commit_sha: str | None = None) -> dict[str, object]:
    skins: dict[str, dict[str, object]] = {}
    skins_root = root / SKINS_DIR_NAME
    if skins_root.is_dir():
        _validate_catalog_root(skins_root)
        names_seen: dict[str, str] = {}
        for folder in sorted(child for child in skins_root.iterdir() if child.is_dir()):
            _validate_skin_folder(folder)
            entry = validate_skin_file(folder / SKIN_FILE_NAME, root)
            name_key = str(entry["name"]).casefold()
            if name_key in names_seen:
                raise ValueError(
                    f"{folder}: the name '{entry['name']}' is already used by skin '{names_seen[name_key]}'"
                )
            names_seen[name_key] = folder.name
            skins[folder.name] = entry
    return {
        "repo": REPO_NAME,
        "branch": BRANCH_NAME,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commit_sha": commit_sha if commit_sha is not None else current_commit_sha(root),
        "skins": skins,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the community skins catalog (SKINS/<id>/panels.json).")
    parser.add_argument("--validate-only", action="store_true", help="Validate only (the default action)")
    parser.parse_args()
    try:
        manifest = build_manifest()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Validated {len(manifest['skins'])} catalog skins.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
