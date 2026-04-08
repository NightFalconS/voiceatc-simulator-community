#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / ".voiceatc" / "color_profiles_manifest.json"
REPO_NAME = "lainoa-software/voiceatc-simulator-community"
BRANCH_NAME = "main"
SCHEMA_VERSION = 1
PROFILE_FILE_NAMES = {
    "colors": "colors.json",
    "style": "style.json",
}
FILE_KIND_BY_NAME = {file_name: kind for kind, file_name in PROFILE_FILE_NAMES.items()}
FILE_KIND_ORDER = ("colors", "style")
ALLOWED_SCOPE_DEPTHS = {2, 3, 4, 5}
HEX_COLOR_RE = re.compile(r"^[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?$")
ALLOWED_NUMERIC_KEYS = {"symbol_size", "traildot_size", "symbol_line_width"}


def _tracked_profile_files(root: Path) -> list[Path]:
    paths: list[Path] = []
    for file_name in PROFILE_FILE_NAMES.values():
        paths.extend(
            path
            for path in root.rglob(file_name)
            if ".git" not in path.parts and ".voiceatc" not in path.parts
        )
    return sorted(paths)


def safe_repo_path(path: Path, root: Path = ROOT) -> str:
    repo_path = path.relative_to(root).as_posix()
    if not repo_path or repo_path.startswith("/") or repo_path.startswith("../") or "/../" in repo_path:
        raise ValueError(f"unsafe repo path '{repo_path}'")
    return repo_path


def _load_json_object(path: Path) -> tuple[dict[str, object], bytes]:
    raw_bytes = path.read_bytes()
    try:
        payload = json.loads(raw_bytes.decode("utf-8"))
    except Exception as exc:
        raise ValueError(f"{path}: invalid JSON ({exc})") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: color profile file must be a JSON object")
    return payload, raw_bytes


def _validate_scope_depth(scope_path: str, path: Path) -> None:
    depth = len([part for part in scope_path.split("/") if part])
    if depth not in ALLOWED_SCOPE_DEPTHS:
        raise ValueError(f"{path}: scope depth must be 2, 3, 4, or 5 segments")


def _validate_hex_color(value: object, key: str, path: Path) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{path}: '{key}' must be a string")
    if not HEX_COLOR_RE.fullmatch(value.strip()):
        raise ValueError(f"{path}: '{key}' must be a 6 or 8 digit hex color")


def validate_colors_file(path: Path, root: Path = ROOT) -> dict[str, object]:
    payload, raw_bytes = _load_json_object(path)
    if not payload:
        raise ValueError(f"{path}: colors.json must not be empty")

    for key, value in payload.items():
        if not isinstance(key, str) or not key.endswith("_color"):
            raise ValueError(f"{path}: colors.json only accepts top-level '*_color' keys")
        _validate_hex_color(value, key, path)

    return {
        "repo_path": safe_repo_path(path, root),
        "sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "size_bytes": len(raw_bytes),
    }


def validate_style_file(path: Path, root: Path = ROOT) -> dict[str, object]:
    payload, raw_bytes = _load_json_object(path)
    if not payload:
        raise ValueError(f"{path}: style.json must not be empty")

    for key, value in payload.items():
        if key == "defined_symbols":
            if not isinstance(value, dict) or not value:
                raise ValueError(f"{path}: 'defined_symbols' must be a non-empty object")
            for symbol_name, symbol_def in value.items():
                if not isinstance(symbol_name, str) or not symbol_name.strip():
                    raise ValueError(f"{path}: defined_symbols keys must be non-empty strings")
                if isinstance(symbol_def, str):
                    raise ValueError(
                        f"{path}: defined_symbols['{symbol_name}'] uses legacy bitmap format; "
                        f"convert to dict with 'type', 'draw', and 'connection_points'"
                    )
                elif isinstance(symbol_def, dict):
                    for required in ("type", "draw", "connection_points"):
                        if required not in symbol_def:
                            raise ValueError(f"{path}: defined_symbols['{symbol_name}'] missing required key '{required}'")
                    if not isinstance(symbol_def["type"], str) or not symbol_def["type"].strip():
                        raise ValueError(f"{path}: defined_symbols['{symbol_name}']['type'] must be a non-empty string")
                    if not isinstance(symbol_def["draw"], str) or not symbol_def["draw"].strip():
                        raise ValueError(f"{path}: defined_symbols['{symbol_name}']['draw'] must be a non-empty string")
                    if not isinstance(symbol_def["connection_points"], list):
                        raise ValueError(f"{path}: defined_symbols['{symbol_name}']['connection_points'] must be an array")
                else:
                    raise ValueError(f"{path}: defined_symbols['{symbol_name}'] must be an object with 'type', 'draw', and 'connection_points'")
            continue
        if key in ALLOWED_NUMERIC_KEYS:
            if not isinstance(value, (int, float)) or value <= 0:
                raise ValueError(f"{path}: '{key}' must be a positive number")
            continue
        if not isinstance(key, str) or not key.endswith("_symbol"):
            raise ValueError(f"{path}: style.json only accepts 'defined_symbols', '*_symbol', and numeric config keys")
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{path}: '{key}' must be a non-empty string")

    return {
        "repo_path": safe_repo_path(path, root),
        "sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "size_bytes": len(raw_bytes),
    }


def validate_profile_directory(profile_dir: Path, profile_files: dict[str, Path], root: Path = ROOT) -> dict[str, object]:
    scope_path = safe_repo_path(profile_dir, root)
    _validate_scope_depth(scope_path, profile_dir)

    missing_kinds = [kind for kind in FILE_KIND_ORDER if kind not in profile_files]
    if missing_kinds:
        raise ValueError(f"{scope_path}: missing color profile files: {', '.join(missing_kinds)}")

    files = {
        "colors": validate_colors_file(profile_files["colors"], root),
        "style": validate_style_file(profile_files["style"], root),
    }
    return {
        "scope_path": scope_path,
        "files": files,
    }


def current_commit_sha(root: Path = ROOT) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        text=True,
    ).strip()


def build_manifest(root: Path = ROOT, commit_sha: str | None = None) -> dict[str, object]:
    profile_candidates: dict[Path, dict[str, Path]] = {}
    for path in _tracked_profile_files(root):
        kind = FILE_KIND_BY_NAME.get(path.name)
        if kind is None:
            continue
        profile_candidates.setdefault(path.parent, {})[kind] = path

    profiles: dict[str, dict[str, object]] = {}
    for profile_dir in sorted(profile_candidates):
        validated_profile = validate_profile_directory(profile_dir, profile_candidates[profile_dir], root)
        scope_path = str(validated_profile["scope_path"])
        if scope_path in profiles:
            raise ValueError(f"duplicate color profile scope '{scope_path}'")
        profiles[scope_path] = {"files": validated_profile["files"]}

    return {
        "schema_version": SCHEMA_VERSION,
        "repo": REPO_NAME,
        "branch": BRANCH_NAME,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commit_sha": commit_sha if commit_sha is not None else current_commit_sha(root),
        "profiles": dict(sorted(profiles.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate split color profiles and generate the community color-profiles manifest.")
    parser.add_argument("--write", action="store_true", help="Write .voiceatc/color_profiles_manifest.json")
    parser.add_argument("--validate-only", action="store_true", help="Validate only, without writing the manifest")
    args = parser.parse_args()

    try:
        manifest = build_manifest()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.write:
        MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Wrote {MANIFEST_PATH.relative_to(ROOT).as_posix()}")
    elif args.validate_only:
        print(f"Validated {len(manifest['profiles'])} color profiles.")
    else:
        print(json.dumps(manifest, indent=2, sort_keys=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
