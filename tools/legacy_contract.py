"""Frozen labels of the default community feed.

Frozen: read by shipped builds (stable 0.6.1.24, open beta 0.6.2.204). These
builds check the ``schema_version`` of every default manifest strictly, so the
values below never change and never gain siblings. New contracts carry no
version keys: a file is identified by its path, readers ignore keys they do not
know, and new content is gated with ``requires`` (see
``documentation/channel-gates.md``). Every producer of the default feed takes
its value from here; ``tools/stable_contract_guard.py`` checks the output
independently.
"""
from __future__ import annotations


# .voiceatc/{mva,runway_configs,sector_data,misc_drawings,color_profiles}_manifest.json
LEGACY_DATASET_MANIFEST_SCHEMA_VERSION = 2
# .voiceatc/release_manifest.json
LEGACY_RELEASE_MANIFEST_SCHEMA_VERSION = 4
# .voiceatc/routes_manifest.json
LEGACY_ROUTES_MANIFEST_SCHEMA_VERSION = 2
# The routes release manifest asset (tools/routes_release_manifest.py)
LEGACY_ROUTES_RELEASE_MANIFEST_SCHEMA_VERSION = 1
# ROUTES/routes_default_manifest.json (the bundled offline fallback)
LEGACY_ROUTES_DEFAULT_MANIFEST_SCHEMA_VERSION = 1
# .voiceatc/constraints_manifest.json
LEGACY_CONSTRAINTS_MANIFEST_SCHEMA_VERSION = 1
# .voiceatc/procedure_options_manifest.json
LEGACY_PROCEDURE_OPTIONS_MANIFEST_SCHEMA_VERSION = 1
# .voiceatc/player_routes_manifest.json
LEGACY_PLAYER_ROUTES_MANIFEST_SCHEMA_VERSION = 1
# .voiceatc/player_routes_status.json
LEGACY_PLAYER_ROUTES_STATUS_SCHEMA_VERSION = 1
# .voiceatc/visual_{procedures,go_arounds,sight_references}_manifest.json and the
# per-airport visual_*.json files they list (open beta reads both with exact keys)
LEGACY_VISUAL_SCHEMA_VERSION = 1
