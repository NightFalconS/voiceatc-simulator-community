# Skins modding guide

A **skin** is one `panels.json` that decides how the session interface looks: colours, fonts, sizes, how each
kind of control is drawn, and which layout each part of the screen uses. A skin changes the look, **never the
features**: every skin shows the same buttons, values and windows, and a skin cannot add, remove or rename one.

- Every key, its type, Generic's value and the values it allows: [skin key reference](skins-reference.md)
  (generated from the schema).
- Where a skin goes and how it ships: [regional skins](session-skins-panels-json.md) (beside a `colors.json`) and
  the [skins catalog](skins-catalog.md) (`SKINS/<id>/`, picked by the player).
- The schema itself: [`tools/interface_contract/interface.schema.json`](../tools/interface_contract/interface.schema.json),
  a pinned copy of the game's `resources/session_skins/interface.schema.json`.

## Quick start

1. Make a folder for your skin and a `panels.json` in it:

   ```json
   {
     "$schema": "../../tools/interface_contract/interface.schema.json",
     "name": "Harbour Blue",
     "author": "Your name",
     "extends": "generic",
     "tokens": { "colors": { "bar": "10233F", "panel": "0E1C33", "accent": "2F6DB5" } }
   }
   ```

   `$schema` is optional; with it, VS Code and other JSON editors autocomplete every key and underline mistakes
   as you type. Point it at the schema from where your file sits.
2. Check it: `python tools/validate_skin.py path/to/panels.json` (see [the validator](#the-validator)).
3. Try it in the game with [live reload](#live-reload), then submit it to the [catalog](skins-catalog.md).

## The five parts

| Part | What it is |
|---|---|
| metadata | `name` (up to 40 characters), `author` (60), `description` (200). Settings > Skin lists the skin by them. |
| `extends` | The skin this one starts from. You write only what differs. |
| `tokens` | Named values: `colors` (role → `RRGGBB` or `RRGGBBAA`, no `#`), `fonts` (role → a bundled font), `type` (role → px), `case` (`as_written` or `upper`), `bevel.width`. |
| `primitives` | How each kind of control looks: `window`, `list`, `field`, `button`, `tick`, `caption`, `bar`, `bar_cell`, `dcb_button`, `status_line`. |
| `components` | Each part of the screen: its layout `mode` and, where the mode has them, `slots` (where each feature sits) and `templates` (its label). |

**Roles.** A primitive never names a colour, a font or a size directly: it names a **role** from `tokens`
(`"text": "value"`, `"fill": "panel"`, `"type": "list"`). Generic defines about thirty colour roles; your skin
may add its own (`"brass": "B08D57"`) and use them in its primitives. The player can recolour any role in
Settings > Skin, so a skin built on roles stays recolourable.

**Fonts** are bundled only: `noto_sans`, `courier_prime`, `barlow_semi_condensed`. A skin cannot ship fonts or
images.

**States.** A primitive's `states` are `normal`, `hover`, `pressed`, `on`, `disabled`, `focused` and `current`.
Each starts from `normal` and changes only what it names. A state sets a `box` (how the background is drawn:
`flat`, `bevel` or `none`, with `fill`, `border`, `pad`, `underline`, `left_bar`...) plus `text`, `font`, `weight`
(400, 600, 700), `type` and `spacing`.

**Sizes** are whole design pixels at interface size 1.0. The game scales them to the window and the player's
interface size, so never pre-scale them.

## Extends

`extends` names the base: `generic` (the default), `scope:<path>` for a regional skin (`scope:L/LE` is the Spain
SACTA skin) or `skin:<id>` for a catalog skin. The base is resolved first, then your file on top:

- objects merge key by key, so `{"tokens": {"colors": {"bar": "000000"}}}` changes one colour and keeps the rest;
- arrays and plain values replace (a `pad` of four numbers is replaced whole);
- a component whose `mode` changes drops the base's `slots` and `templates`, so a base's layout never leaks into
  another mode; its sizes and boxes still inherit;
- a chain is followed at most 4 deep. In the game, an unknown base or a loop starts from Generic; the validator
  reports it as an error.

## Slots and parity

Components with slots (today: `top`, and `bottom` when it is merged into the top) place **every one of their
features exactly once**. That is the parity rule: a skin can move a feature, never drop or duplicate one.

| Mode | Slots |
|---|---|
| `top` `cell_row` (Generic) | `left`, `right`: lists of feature ids, in order |
| `top` `dcb_grid` | `columns`: groups `{"ids": [...], "width": 1}` (two ids stack as halves of one column); `status`: status lines, each a list of ids read left to right |

Top features: `airport`, `qnh`, `tl`, `rwy`, `radio`, `com`, `tfc`, `vprof`, `clock`, `warp`, `pause`,
`settings`. With `bottom` `merged_into_top`, the bottom's `maps`, `procs`, `airspaces`, `tag`, `range`, `vector`,
`clr_qdm`, `clr_routes` must also sit in the top's slots. `templates` give a feature's label: `{value}` is its
live value and `\n` a line break (`"RANGE\n{value}"`).

Some modes depend on another component: `value_popup`, `wpt` or `menus` in `dock_strip`, and `bottom` in
`merged_into_top`, need `top` in `dcb_grid` (they dock under it). `primitives.window.close` `cell` needs
`primitives.window.top_strip` `bar`.

## Capabilities

There are no version numbers in a skin. Every mode or window feature that is not Generic's is a **capability**
(`interface.top.dcb_grid`, `interface.radio.status_line`, `interface.window.close.hidden`, ...), derived from what
the skin uses. A game build that lacks one of them shows Generic instead of a half-drawn skin, so a skin written
for a newer build never breaks an older one. The validator reports a mode the pinned game does not know as
`needs capability interface.<component>.<mode>, which this build lacks`, with a hint when it looks like a typo.
The full list is at the end of the [key reference](skins-reference.md#capabilities-the-game-supports).

## The validator

`tools/validate_skin.py` checks skins with the same rules as the game's strict mode
(`InterfaceSpec.strict_errors`): the schema (types, allowed values, ranges, unknown keys), role references,
parity, the mode rules above and capabilities. Every error has its JSON path, and a "did you mean" hint when a
known name is close:

```text
$ python tools/validate_skin.py my-skin/panels.json
my-skin/panels.json: 3 error(s)
  tokens.colors.bar: '#10233F' is not a valid value
  primitives.list.row_heigth: unknown key (did you mean 'row_height'?)
  components.wpt.mode: dock_strip needs components.top.mode dcb_grid
```

It takes any number of files and exits with 1 when one has an error. `extends` resolves inside this repository
(`scope:L/LE` is `L/LE/panels.json`, `skin:harbour-blue` is `SKINS/harbour-blue/panels.json`; `--root` picks
another checkout). Pull requests run it on every `panels.json` (the **Validate Skins Catalog** check), and the
colour-profile and catalog checks run the same rules.

The game itself is **tolerant**: it skips an unknown key or a bad value with one debug line and keeps the
inherited value, and it shows Generic when a rule breaks or a capability is missing. The validator is strict so
those mistakes never reach players.

The schema is a pinned copy (`tools/interface_contract/contract.json` names the game commit). Maintainers refresh
it with `python tools/sync_interface_contract.py --game <game checkout> --ref origin/closed-beta`, then
`python tools/skin_reference.py` to regenerate the key reference; a test fails if either copy is edited by hand.
The copies must retain the pinned game's exact bytes, including whitespace. `.prettierignore` excludes
`tools/interface_contract/`, and the formatting job runs the skin tests before committing. If a formatter
changes a copy, re-run the sync at the recorded `game_commit`; do not update its hash to accept the changed bytes.

## Live reload

Work on a skin while a session runs:

1. Put it in a **local override** colour-profile scope: the scope folder of an airport you can open, under
   `%APPDATA%\VoiceATCSimulator\community\color_profiles\` (for example `...\color_profiles\L\LE\`), with a
   `colors.json`, your `panels.json` and a `local_override.json` containing `{"local_override": true}`. The game
   then uses your files for that scope instead of the downloaded ones.
2. Start a session at an airport in that scope (or pick the skin in Settings > Skin).
3. Save `panels.json`. The game re-applies it within about a second.

When the saved file has an error, the game **keeps the last good skin** and lists the errors (the same messages
as the validator) in a small panel in the corner of the screen; fix the file and save again and the panel goes
away. The game checks the file twice a second, and only for a local-override skin (a `local_override.json` in
its scope folder or any parent, including `community\local_override.json`) or a debug build started with
`-- --skin-live-reload`; players with downloaded skins never pay for it or see the panel.

## Cookbook

### A three-colour recolour

```json
{
  "name": "Harbour Blue",
  "extends": "generic",
  "tokens": { "colors": { "bar": "10233F", "panel": "0E1C33", "accent": "2F6DB5" } }
}
```

### A minimal dark skin

Darker roles, capitals, a shorter title bar and denser lists with a text mark on the current value:

```json
{
  "name": "Night Shift",
  "author": "Jane Modder",
  "extends": "generic",
  "tokens": {
    "colors": {
      "bar": "05070B", "edge": "1A1F2A", "panel": "080B11", "title": "10141C",
      "accent": "1E2A3D", "well": "05070B", "button": "10141C", "field": "05070B",
      "text": "A7B0C0", "dim": "5D6678", "value": "E4E8F0", "scope": "020305"
    },
    "case": "upper"
  },
  "primitives": {
    "window": { "title": { "height": 22 } },
    "list": { "row_height": 20, "current": { "mark": "<", "left_bar": 0 } }
  }
}
```

### The radio as a status line

The radio state (RX, TX, BLOCKED, PARSING) as plain text instead of coloured pills:

```json
{
  "name": "Quiet Radio",
  "extends": "generic",
  "components": { "radio": { "mode": "status_line" } }
}
```

### A STARS-like DCB bar

Square buttons across the top, the bottom bar merged into them, the menus docked under them and the status
lines (clock, airport, QNH; runways; radio) on the scope. Every top and bottom feature appears once:

```json
{
  "name": "Square Buttons",
  "extends": "generic",
  "components": {
    "top": {
      "mode": "dcb_grid",
      "slots": {
        "columns": [
          {"ids": ["maps"]}, {"ids": ["procs"]}, {"ids": ["airspaces"]},
          {"ids": ["tag", "range"]}, {"ids": ["vector", "tl"]}, {"ids": ["com", "tfc"]},
          {"ids": ["vprof"]}, {"ids": ["warp", "pause"]}, {"ids": ["clr_qdm", "clr_routes"]},
          {"ids": ["settings"], "width": 1.5}
        ],
        "status": [["clock", "airport", "qnh"], ["rwy"], ["radio"]]
      },
      "templates": { "range": "RANGE\n{value}", "airspaces": "AIR\nSPACE" }
    },
    "bottom": { "mode": "merged_into_top" },
    "menus": { "mode": "dock_strip" }
  }
}
```

The full US look adds the STARS colours, the `dcb_button` and `status_line` looks and the paper strip: read
[`K/panels.json`](../K/panels.json). The Spain SACTA look (thin window bars, bevelled cells, paper strips) is
[`L/LE/panels.json`](../L/LE/panels.json). Both extend Generic and are complete worked examples.
