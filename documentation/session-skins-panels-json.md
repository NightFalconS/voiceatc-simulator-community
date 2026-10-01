# Session skins: `panels.json`

> Reference for modders. It is written to move into the
> [modding wiki](https://github.com/lainoa-software/voiceatc-simulator-community/wiki) as it stands.

A **skin** changes how the session interface looks: the bars across the screen, the panels, the datablock
popups and the traffic strip. It lives in a `panels.json` placed beside a colour profile's `colors.json`.

## A skin changes the look, never the features

Every skin shows the **same features** the Generic interface has. A skin can change colours, fonts, letter
case, bevels and frame styles. It can never add a feature, remove one, rename one, or draw a field of a real
system that the game does not simulate. That is why the key list below is closed: any key that is not on it is
rejected by the repository check, and the game also ignores it.

## Where it goes

Put `panels.json` in the same folder as the `colors.json` it belongs to: a region, nationality, FIR or ARTCC,
ACC group or terminal folder (see the [content hierarchy](CONTENT_HIERARCHY.md)).

- A `panels.json` is only accepted where a `colors.json` sits in the same folder.
- The skin is optional. A colour profile without one uses the Generic interface.
- Precedence is the one `colors.json` uses. The game picks the deepest scope that has a colour profile, then
  takes the `panels.json` **next to that `colors.json`**. A terminal area without its own colour profile
  therefore takes its parent's skin, exactly as it takes its parent's colours. A player's local override of a
  scope wins over the downloaded one.
- The Spain (`L/LE/panels.json`, the SACTA look) and US (`K/panels.json`, the legacy STARS look) skins ship in
  this file at those folders. They are complete examples of every key.

## Keys

Every key is optional. A missing key keeps the Generic value. A key with an invalid value is rejected by the
repository check (and ignored by the game, which keeps Generic for it).

| Key | Generic | Accepts |
|---|---|---|
| `frame_style` | `window` | `window` (title bar), `sacta` (thin bar plus title strip), `none` (text on the scope) |
| `bar_style` | `bars` | `bars` (text bars), `cells` (bevelled cells), `dcb` (square buttons) |
| `strip_style` | `dark` | `dark`, `paper_es` (printed strip), `paper_us` (terminal strip) |
| `text_case` | `as_written` | `as_written`, `upper` (chrome and lists) |
| `bevel` | `0` | a whole number from `0` to `8`: raised and sunken bevel width in pixels |
| `bar_color` | `1F2535` | bar background |
| `edge_color` | `394258` | borders and cell dividers |
| `panel_color` | `1B2130` | panel body |
| `title_color` | `333B50` | title bar |
| `accent_color` | `4B546D` | focused title, hover row, toggle on |
| `well_color` | `141926` | lists and fields |
| `button_color` | `2A3142` | buttons |
| `text_color` | `CDD3E0` | body text |
| `dim_color` | `8891A6` | captions and keys |
| `on_color` | `9DB0DA` | current-value mark, toggle underline, focused field |
| `value_color` | `FFFFFF` | values and titles |
| `strip_color` | `23262E` | the dark traffic strip |
| `bevel_light_color` | `394258` | the lit edge of a raised bevel |
| `bevel_dark_color` | `141926` | the shaded edge of a raised bevel |
| `selection_color` | `4B546D` | selection bar behind the picked row |
| `selection_text_color` | `FFFFFF` | text on the selection bar |
| `field_color` | `141926` | background of edit fields |
| `field_text_color` | `FFFFFF` | text typed in edit fields |
| `inactive_color` | `333B50` | an unfocused window's title or bar |
| `ok_color` | `9FE0B8` | status text: all good |
| `warn_color` | `F2C14E` | status text: caution |
| `alert_color` | `FF7A7A` | status text: alert |
| `clock_color` | `FFFFFF` | the clock |
| `hover_text_color` | `FFFFFF` | text of the row under the pointer |
| `strip_text_color` | `CDD3E0` | text on the dark traffic strip |
| `scope_color` | `0E131C` | the radar scope background |
| `text_font` | `noto_sans` | chrome text |
| `data_font` | `courier_prime` | data such as idents and numbers |

Rules for the values:

- Every `*_color` is plain hex, `RRGGBB` or `RRGGBBAA`, **without** a `#`, like `colors.json`. No spaces.
- `text_font` and `data_font` are one of `noto_sans`, `courier_prime`, `barlow_semi_condensed`.
  A skin cannot load its own font files.
- `bevel` is an integer written without a decimal point (`2`, not `2.0`).
- The file is a JSON object and cannot be empty.

The traffic strip's flight-type holder colours are the same in every skin and are not keys.

## Name, author and description

Three more optional keys describe the skin to people. The Skin section of the game lists a skin by them. They are
text, never skin values, and the game does not apply them:

| Key | Accepts |
|---|---|
| `name` | one line of text, 1 to 40 characters, no space at either end. Without it the game names the skin from its folder, for example `L/LE` |
| `author` | one line of text, 1 to 60 characters |
| `description` | one line of text, 1 to 200 characters |

The file must still set at least one look key above. The Spain and US skins are named `Spain (SACTA)` and
`US (STARS)`. The [skins catalog](skins-catalog.md) (`SKINS/<id>/panels.json`, picked by the player instead of
by airport) requires `name` and `author`.

## Minimal example

A skin that keeps Generic and only makes the bars bevelled cells in upper case:

```json
{
  "bar_style": "cells",
  "text_case": "upper",
  "bevel": 2
}
```

## Checks and shipping

Every pull request that touches a `panels.json` runs the same check as `colors.json` and `style.json`
(`python tools/color_profiles_manifest.py --validate-only`, also part of the required `validate` check). The
release then lists `panels.json` in the colour-profiles manifest for that scope, with its hash and size, and
packs it in the colour-profiles archive that the game downloads. Do not edit the generated manifest by hand.
The game reads `panels.json` from the archive only from the simulator version that introduced session
skins. Maintainers: do not merge the pull request that adds the first `panels.json` content files (the Spain
and US skins) until that version is the minimum supported one and the game build that renders those skins has
shipped, because older versions reject a colour-profiles archive that contains a file they do not list.
