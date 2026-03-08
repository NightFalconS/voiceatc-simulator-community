#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / ".voiceatc" / "runway_configs_manifest.json"
REPO_NAME = "lainoa-software/voiceatc-simulator-community"
BRANCH_NAME = "main"
SCHEMA_VERSION = 1


def runway_files() -> list[Path]:
    return sorted(
        path for path in ROOT.rglob("runway_config.json")
        if ".git" not in path.parts and ".voiceatc" not in path.parts
    )


def ensure_text_field(value: object, label: str, path: Path) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{path}: '{label}' must be a string")
    text = value.strip()
    if not text:
        raise ValueError(f"{path}: '{label}' must not be empty")
    return text


def validate_runway_file(path: Path) -> dict[str, object]:
    raw_bytes = path.read_bytes()
    try:
        payload = json.loads(raw_bytes.decode("utf-8"))
    except Exception as exc:
        raise ValueError(f"{path}: invalid JSON ({exc})") from exc

    if not isinstance(payload, dict):
        raise ValueError(f"{path}: runway config must be a JSON object")

    airport = ensure_text_field(payload.get("airport"), "airport", path).upper()
    parent_folder = path.parent.name.strip().upper()
    if airport != parent_folder:
        raise ValueError(f"{path}: airport '{airport}' must match parent folder '{parent_folder}'")

    configs = payload.get("runway_configurations", payload.get("runway_configs"))
    if not isinstance(configs, list) or not configs:
        raise ValueError(f"{path}: missing non-empty runway_configurations/runway_configs array")

    seen_ids: set[str] = set()
    for index, row in enumerate(configs):
        if not isinstance(row, dict):
            raise ValueError(f"{path}: config row {index} must be an object")

        config_id = ensure_text_field(row.get("id"), "id", path).upper()
        if config_id in seen_ids:
            raise ValueError(f"{path}: duplicate config id '{config_id}'")
        seen_ids.add(config_id)

        if "name" in row and not isinstance(row["name"], str):
            raise ValueError(f"{path}: config '{config_id}' field 'name' must be a string")

        for key in ("arr", "dep"):
            value = row.get(key)
            if not isinstance(value, (str, list)):
                raise ValueError(f"{path}: config '{config_id}' field '{key}' must be a string or array")

    return {
        "airport": airport,
        "repo_path": path.relative_to(ROOT).as_posix(),
        "sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "size_bytes": len(raw_bytes),
    }


def current_commit_sha() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
    ).strip()


def build_manifest() -> dict[str, object]:
    airports: dict[str, dict[str, object]] = {}
    for path in runway_files():
        entry = validate_runway_file(path)
        airport = str(entry["airport"])
        if airport in airports:
            raise ValueError(f"duplicate airport '{airport}' across runway config files")
        airports[airport] = {
            "repo_path": entry["repo_path"],
            "sha256": entry["sha256"],
            "size_bytes": entry["size_bytes"],
        }

    return {
        "schema_version": SCHEMA_VERSION,
        "repo": REPO_NAME,
        "branch": BRANCH_NAME,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commit_sha": current_commit_sha(),
        "airports": dict(sorted(airports.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate runway_config.json files and generate the community runway-configs manifest.")
    parser.add_argument("--write", action="store_true", help="Write .voiceatc/runway_configs_manifest.json")
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
        print(f"Validated {len(manifest['airports'])} runway config files.")
    else:
        print(json.dumps(manifest, indent=2, sort_keys=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
