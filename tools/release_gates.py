#!/usr/bin/env python3
"""Channel gates for community releases.

Two maintainer-edited files decide what each live game build may download:

- ``.voiceatc/gates.json`` marks new content (a file kind, a repo path glob or a
  route lane) with ``min_game_version`` and/or ``channels``.
- ``release/live_versions.json`` lists the game version live on each Steam
  channel.

The default manifests and zips (the paths every build already reads) keep an
entry only when every live channel passes its gate, so they never carry
anything the oldest live build would reject. The v3 manifests under
``.voiceatc/v3/`` keep everything plus the gate fields; only builds that read
v3 filter entries themselves.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
GATES_PATH = Path(".voiceatc") / "gates.json"
LIVE_VERSIONS_PATH = Path("release") / "live_versions.json"
V3_DIR = Path(".voiceatc") / "v3"
GATES_SCHEMA_VERSION = 1
V3_SCHEMA_VERSION = 3
CHANNELS = ("stable", "open-beta", "closed-beta")
# Datasets whose default output this producer filters (the release zips).
FILTERED_DATASETS = ("mva", "runway_configs", "sector_data", "misc_drawings", "color_profiles")
# Datasets served by lane (the API worker); a lane gate never touches a default path.
LANE_DATASETS = ("routes", "voice_priors", "snapshots")
GATE_SELECTORS = ("kind", "path", "lane")
GATE_RULES = ("min_game_version", "channels")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+\.\d+$")
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
KIND_RE = re.compile(r"^[a-z][a-z0-9_]*$")
LANE_RE = re.compile(r"^[a-z][a-z0-9_-]*$")


def parse_version(text: object) -> tuple[int, int, int, int]:
    if not isinstance(text, str) or not VERSION_RE.fullmatch(text.strip()):
        raise ValueError(f"version must be four dot-separated numbers, got {text!r}")
    major, minor, patch, build = (int(part) for part in text.strip().split("."))
    return major, minor, patch, build


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"{path}: invalid JSON ({exc})") from exc


def validate_gates(payload: object, label: str = str(GATES_PATH)) -> list[dict[str, object]]:
    if not isinstance(payload, dict):
        raise ValueError(f"{label}: must be a JSON object")
    if set(payload) != {"schema_version", "gates"}:
        raise ValueError(f"{label}: keys must be exactly schema_version and gates")
    if payload["schema_version"] != GATES_SCHEMA_VERSION:
        raise ValueError(f"{label}: schema_version must be {GATES_SCHEMA_VERSION}")
    gates = payload["gates"]
    if not isinstance(gates, list):
        raise ValueError(f"{label}: gates must be an array")
    result: list[dict[str, object]] = []
    for index, gate in enumerate(gates):
        where = f"{label}: gates[{index}]"
        if not isinstance(gate, dict):
            raise ValueError(f"{where} must be an object")
        unknown = set(gate) - {"dataset", *GATE_SELECTORS, *GATE_RULES}
        if unknown:
            raise ValueError(f"{where} has unknown keys {sorted(unknown)}")
        dataset = gate.get("dataset")
        selectors = [key for key in GATE_SELECTORS if key in gate]
        if len(selectors) != 1:
            raise ValueError(f"{where} needs exactly one of kind, path or lane")
        selector = selectors[0]
        if selector == "lane":
            if dataset not in LANE_DATASETS:
                raise ValueError(f"{where}: lane gates apply to {', '.join(LANE_DATASETS)}")
            if not isinstance(gate["lane"], str) or not LANE_RE.fullmatch(gate["lane"]):
                raise ValueError(f"{where}: lane must be a lowercase name")
        else:
            if dataset not in FILTERED_DATASETS:
                raise ValueError(f"{where}: dataset must be one of {', '.join(FILTERED_DATASETS)}")
            value = gate[selector]
            if selector == "kind" and (not isinstance(value, str) or not KIND_RE.fullmatch(value)):
                raise ValueError(f"{where}: kind must be a lowercase file kind such as 'panels'")
            if selector == "path":
                if not isinstance(value, str) or not value.strip() or value.startswith("/") or ".." in value:
                    raise ValueError(f"{where}: path must be a repo-relative path or glob")
        if not any(key in gate for key in GATE_RULES):
            raise ValueError(f"{where} needs min_game_version and/or channels")
        if "min_game_version" in gate:
            parse_version(gate["min_game_version"])
        if "channels" in gate:
            channels = gate["channels"]
            if not isinstance(channels, list) or not channels:
                raise ValueError(f"{where}: channels must be a non-empty array")
            for channel in channels:
                if channel not in CHANNELS:
                    raise ValueError(f"{where}: unknown channel {channel!r}")
            if len(set(channels)) != len(channels):
                raise ValueError(f"{where}: duplicate channel")
        result.append(dict(gate))
    return result


def validate_live_versions(payload: object, label: str = str(LIVE_VERSIONS_PATH)) -> dict[str, str]:
    if not isinstance(payload, dict):
        raise ValueError(f"{label}: must be a JSON object")
    if set(payload) != {*CHANNELS, "updated_at"}:
        raise ValueError(f"{label}: keys must be exactly {', '.join(CHANNELS)} and updated_at")
    for channel in CHANNELS:
        parse_version(payload[channel])
    if not isinstance(payload["updated_at"], str) or not TIMESTAMP_RE.fullmatch(payload["updated_at"]):
        raise ValueError(f"{label}: updated_at must be YYYY-MM-DDTHH:MM:SSZ")
    return {channel: str(payload[channel]) for channel in CHANNELS}


def load_gates(root: Path = ROOT) -> list[dict[str, object]]:
    path = root / GATES_PATH
    if not path.is_file():
        return []
    return validate_gates(_read_json(path), str(path))


def load_live_versions(root: Path = ROOT) -> dict[str, str]:
    path = root / LIVE_VERSIONS_PATH
    return validate_live_versions(_read_json(path), str(path))


def passes_every_live_channel(rule: dict[str, object], live_versions: dict[str, str]) -> bool:
    """True when every live build, on its own channel, would keep this entry."""
    for channel, version in live_versions.items():
        channels = rule.get("channels")
        if isinstance(channels, list) and channel not in channels:
            return False
        minimum = rule.get("min_game_version")
        if minimum is not None and parse_version(version) < parse_version(minimum):
            return False
    return True


def _merge_rules(gates: list[dict[str, object]]) -> dict[str, object]:
    """Several gates on one item: the highest minimum and the common channels."""
    merged: dict[str, object] = {}
    for gate in gates:
        if "min_game_version" in gate:
            current = merged.get("min_game_version")
            if current is None or parse_version(gate["min_game_version"]) > parse_version(current):
                merged["min_game_version"] = gate["min_game_version"]
        if "channels" in gate:
            current_channels = merged.get("channels")
            allowed = list(gate["channels"])
            if isinstance(current_channels, list):
                allowed = [channel for channel in current_channels if channel in allowed]
            merged["channels"] = [channel for channel in CHANNELS if channel in allowed]
    return merged


def _matching_gates(
    gates: list[dict[str, object]],
    *,
    kind: str | None,
    paths: list[str],
) -> list[dict[str, object]]:
    matched: list[dict[str, object]] = []
    for gate in gates:
        if "kind" in gate and kind is not None and gate["kind"] == kind:
            matched.append(gate)
        elif "path" in gate and any(fnmatch.fnmatchcase(path, str(gate["path"])) for path in paths):
            matched.append(gate)
    return matched


def apply_gates(
    dataset: str,
    entries: dict[str, object],
    *,
    gates: list[dict[str, object]],
    live_versions: dict[str, str],
    archive_sources: dict[str, str] | None = None,
    required_kinds: tuple[str, ...] | None = None,
) -> dict[str, object]:
    """Split one dataset's entries into the default view and the annotated v3 list.

    ``entries`` is the manifest's entry map (airports, bundles or profiles). An
    entry is either one file (``repo_path``) or a ``files`` map by kind. A gated
    file the live builds do not all pass leaves the default entry; when that
    removes a required kind (``required_kinds``; ``None`` means every kind the
    entry has) or the last file, the whole entry leaves. Ungated data returns
    ``default`` equal to ``entries`` (same objects, same order).
    """
    dataset_gates = [gate for gate in gates if gate.get("dataset") == dataset and "lane" not in gate]
    sources = archive_sources or {}
    default: dict[str, object] = {}
    v3_entries: list[dict[str, object]] = []
    for key, entry in entries.items():
        if not isinstance(entry, dict):
            raise ValueError(f"{dataset}: entry '{key}' must be an object")
        v3_entry: dict[str, object] = {"id": key}
        files = entry.get("files")
        if isinstance(files, dict):
            kept_files: dict[str, object] = {}
            v3_files: dict[str, object] = {}
            dropped_kinds: list[str] = []
            for kind, file_entry in files.items():
                repo_path = str(file_entry.get("repo_path", "")) if isinstance(file_entry, dict) else ""
                paths = [repo_path, sources.get(repo_path, repo_path)]
                rule = _merge_rules(_matching_gates(dataset_gates, kind=kind, paths=paths))
                v3_files[kind] = {**file_entry, **rule} if rule else file_entry
                if rule and not passes_every_live_channel(rule, live_versions):
                    dropped_kinds.append(kind)
                else:
                    kept_files[kind] = file_entry
            required = tuple(files) if required_kinds is None else required_kinds
            entry_survives = bool(kept_files) and not any(kind in required for kind in dropped_kinds)
            if entry_survives:
                default[key] = entry if not dropped_kinds else {**entry, "files": kept_files}
            v3_entry.update({**entry, "files": v3_files})
        else:
            repo_path = str(entry.get("repo_path", ""))
            paths = [repo_path, sources.get(repo_path, repo_path)]
            rule = _merge_rules(_matching_gates(dataset_gates, kind=None, paths=paths))
            if not rule or passes_every_live_channel(rule, live_versions):
                default[key] = entry
            v3_entry.update({**entry, **rule})
        v3_entries.append(v3_entry)
    return {"default": default, "v3_entries": v3_entries}


def entry_repo_paths(entries: dict[str, object]) -> list[str]:
    paths: set[str] = set()
    for entry in entries.values():
        if not isinstance(entry, dict):
            continue
        files = entry.get("files")
        if isinstance(files, dict):
            paths.update(str(item["repo_path"]) for item in files.values() if isinstance(item, dict))
        elif "repo_path" in entry:
            paths.add(str(entry["repo_path"]))
    return sorted(paths)


def build_v3_manifest(
    *,
    dataset: str,
    v3_entries: list[dict[str, object]],
    repo: str,
    release_tag: str,
    commit_sha: str,
    published_at: str,
    asset: dict[str, object] | None,
    download_url: str = "",
) -> dict[str, object]:
    manifest: dict[str, object] = {
        "schema_version": V3_SCHEMA_VERSION,
        "dataset": dataset,
        "repo": repo,
        "release_tag": release_tag.strip(),
        "commit_sha": commit_sha.strip(),
        "published_at": published_at.strip(),
        "generated_at": published_at.strip(),
        "entry_count": len(v3_entries),
        "entries": v3_entries,
    }
    if asset is not None:
        manifest["asset_name"] = str(asset["asset_name"])
        manifest["download_url"] = download_url
        manifest["sha256"] = str(asset["sha256"])
        manifest["size_bytes"] = int(asset["size_bytes"])
    return manifest


def v3_manifest_path(dataset: str, root: Path = ROOT) -> Path:
    return root / V3_DIR / f"{dataset}_manifest.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate .voiceatc/gates.json and release/live_versions.json.")
    parser.add_argument("--validate-only", action="store_true", help="Validate both files (the default action)")
    parser.parse_args()
    try:
        gates = load_gates(ROOT)
        live_versions = load_live_versions(ROOT)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    oldest = min(live_versions.values(), key=parse_version)
    print(f"Validated {len(gates)} gates; live versions {live_versions} (oldest {oldest}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
