# Channel gates: shipping new content to one game channel first

Every game build reads the same community feed, whatever its Steam channel. Stable
(0.6.1.24) and open beta (0.6.2.204) are strict: a file kind they do not know, or a zip
entry their manifest does not list, fails the whole dataset for those players. Gates let
new content reach the builds that can use it, and only those.

## The two files

`.voiceatc/gates.json` (edited by maintainers, never by CI):

```json
{
  "schema_version": 1,
  "gates": [
    { "dataset": "color_profiles", "kind": "panels", "min_game_version": "0.6.2.380" }
  ]
}
```

A gate names a `dataset` and exactly one selector:

| Selector | Matches | Example |
|---|---|---|
| `kind` | a file kind inside an entry (`panels`, `style`, …) | `{"dataset": "color_profiles", "kind": "panels", …}` |
| `path` | a repo path; `*` matches anything, including `/` | `{"dataset": "mva", "path": "E/ED/EDDM/*", …}` |
| `lane` | a route lane served by the API worker | `{"dataset": "routes", "lane": "next", …}` |

and at least one rule:

- `min_game_version`: the four-part game version that first understands the content.
- `channels`: the Steam channels allowed (`stable`, `open-beta`, `closed-beta`). Leave it out
  to allow every channel.

Gateable datasets: `mva`, `runway_configs`, `sector_data`, `misc_drawings`,
`color_profiles` (kind and path gates); `routes`, `voice_priors`, `snapshots` (lane gates,
read by the API worker, never by this release).

`release/live_versions.json` lists the game version live on each channel:

```json
{ "stable": "0.6.1.24", "open-beta": "0.6.2.204", "closed-beta": "0.6.2.374",
  "updated_at": "2026-10-01T00:00:00Z" }
```

Update it whenever a Steam build goes live on a channel.

## What the daily release does with them

For each zip dataset the release writes two outputs:

1. **Default** (`.voiceatc/<dataset>_manifest.json` and `<asset>.zip`): exactly today's
   format. An entry stays when it has no gate, or when every live channel passes its gate.
   A gated file that some live build would not pass is left out of the manifest and the zip.
   When that removes a required file (a profile's `colors`, any sector-data file), the whole
   entry is left out. With no gates, the default output is byte-identical to before.
2. **v3** (`.voiceatc/v3/<dataset>_manifest.json` and `<asset>-full.zip`): everything, with
   the gate fields copied onto the gated entry (path gates on single-file entries) or file
   (`files.<kind>`). `schema_version` is 3 and `entries` is a list; each entry has an `id`
   (the airport, bundle or scope key) plus today's entry fields. Game builds that read v3
   keep an entry or file when `min_game_version` ≤ their version and `channels` is absent
   or contains their channel. Old builds never read v3 paths.

Before anything is published, `tools/stable_contract_guard.py` replays the stable 0.6.1.24
parser rules on every default manifest and zip (schema 2, exact top-level and entry keys,
known file kinds only, every zip entry listed and hash-matched, counts equal) and the open
beta exact-key rule on the visual manifests. A failure stops the release.

## Recipes

- **New content for closed beta only:** add a gate with `"channels": ["closed-beta"]`
  (plus `min_game_version` if older closed-beta builds cannot read it).
- **Promote to open beta:** add `open-beta` to `channels`.
- **Everyone can read it:** once every channel's live version is at or above
  `min_game_version` (check `release/live_versions.json`), remove the gate. The content then
  appears in the default output on the next release.

Check your edit locally:

```
python tools/release_gates.py --validate-only
python -m unittest discover -s tests -p "test_*.py"
```

Contributors do not edit gates. If a pull request adds a new file kind or a new field, a
maintainer adds the gate in the same pull request so it never reaches stable players early.
