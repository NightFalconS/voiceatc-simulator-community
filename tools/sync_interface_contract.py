#!/usr/bin/env python3
"""Refresh the vendored copy of the game's interface contract (``tools/interface_contract/``).

The skin validator (``tools/validate_skin.py``) checks a ``panels.json`` with the same rules
as the game's strict mode, so it needs four things from the game repository, pinned to one
game commit:

- ``interface.schema.json``  (``resources/session_skins/interface.schema.json``)
- ``generic.panels.json``    (``resources/session_skins/generic/panels.json``, the base)
- the feature registry       (``SessionFeatures.REGISTRY``, ``scripts/ui/session/session_features.gd``)
- the interface capabilities (``BuildCapabilities.SUPPORTED``, ``scripts/core/build_capabilities.gd``)

Run it against a checkout of the game when the game's schema changes::

    python tools/sync_interface_contract.py --game ../Project-Emerald-Upgrade --ref origin/closed-beta

It writes ``contract.json`` with the game commit, the registry, the capabilities and the
sha256 of both copied files. ``tests/test_validate_skin.py`` fails when a vendored file no
longer matches its pinned hash, so the copies are never edited by hand.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

CONTRACT_DIR = Path(__file__).resolve().parent / "interface_contract"
CONTRACT_FILE = "contract.json"
SOURCES = {
    "interface.schema.json": "resources/session_skins/interface.schema.json",
    "generic.panels.json": "resources/session_skins/generic/panels.json",
}
FEATURES_SOURCE = "scripts/ui/session/session_features.gd"
CAPABILITIES_SOURCE = "scripts/core/build_capabilities.gd"


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git(game: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(game), *args])


def parse_registry(source: str) -> dict[str, list[str]]:
    """``const REGISTRY := { ... }`` from session_features.gd as a dict."""
    match = re.search(r"const REGISTRY := (\{.*?\n\})", source, re.S)
    if not match:
        raise ValueError(f"{FEATURES_SOURCE}: no REGISTRY block")
    block = re.sub(r",(\s*[\]}])", r"\1", match.group(1))
    return json.loads(block)


def parse_capabilities(source: str) -> list[str]:
    """The ``interface.*`` names of ``SUPPORTED`` in build_capabilities.gd."""
    match = re.search(r"const SUPPORTED: PackedStringArray = \[(.*?)\n\]", source, re.S)
    if not match:
        raise ValueError(f"{CAPABILITIES_SOURCE}: no SUPPORTED block")
    lines = [line.split("#", 1)[0] for line in match.group(1).splitlines()]
    names = re.findall(r'"([a-z0-9_.]+)"', "\n".join(lines))
    return sorted(name for name in names if name.startswith("interface."))


def sync(game: Path, ref: str, out_dir: Path = CONTRACT_DIR) -> dict[str, object]:
    commit = _git(game, "rev-parse", ref).decode().strip()
    out_dir.mkdir(parents=True, exist_ok=True)
    files: dict[str, str] = {}
    for name, source in SOURCES.items():
        data = _git(game, "show", f"{commit}:{source}")
        (out_dir / name).write_bytes(data)
        files[name] = sha256_of(data)
    contract = {
        "game_commit": commit,
        "sources": SOURCES,
        "files": files,
        "features": parse_registry(_git(game, "show", f"{commit}:{FEATURES_SOURCE}").decode()),
        "capabilities": parse_capabilities(
            _git(game, "show", f"{commit}:{CAPABILITIES_SOURCE}").decode()
        ),
    }
    (out_dir / CONTRACT_FILE).write_text(
        json.dumps(contract, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    return contract


def main() -> int:
    parser = argparse.ArgumentParser(description="Vendor the game's interface contract.")
    parser.add_argument("--game", required=True, type=Path, help="A checkout of the game repository")
    parser.add_argument("--ref", default="origin/closed-beta", help="Game commit or ref to pin")
    args = parser.parse_args()
    contract = sync(args.game, args.ref)
    print(f"Pinned the interface contract to game commit {contract['game_commit']}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
