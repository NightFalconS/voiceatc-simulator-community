# Session skins: `panels.json`

> Reference for modders. It is written to move into the
> [modding wiki](https://github.com/lainoa-software/voiceatc-simulator-community/wiki) as it stands.

A **skin** changes how the session interface looks: the bars across the screen, the panels, the datablock
popups and the traffic strip. It is one `panels.json` in the interface language: metadata, `extends`, `tokens`,
`primitives` and `components`. How to write one: [skins modding guide](skins-modding.md). Every key, its type,
Generic's value and the values it allows: [skin key reference](skins-reference.md).

## A skin changes the look, never the features

Every skin shows the **same features** the Generic interface has. A skin can change colours, fonts, sizes, how
each control is drawn and which layout mode each part of the screen uses. It can never add a feature, remove
one, rename one, or draw a field of a real system that the game does not simulate. The key set is closed: an
unknown key is rejected by the repository check (with a "did you mean" hint) and skipped by the game.

## Where it goes

Put `panels.json` in the same folder as the `colors.json` it belongs to: a region, nationality, FIR or ARTCC,
ACC group or terminal folder (see the [content hierarchy](CONTENT_HIERARCHY.md)).

- A `panels.json` is only accepted where a `colors.json` sits in the same folder.
- The skin is optional. A colour profile without one uses the Generic interface.
- Precedence is the one `colors.json` uses. The game picks the deepest scope that has a colour profile, then
  takes the `panels.json` **next to that `colors.json`**. A terminal area without its own colour profile
  therefore takes its parent's skin, exactly as it takes its parent's colours. A player's local override of a
  scope wins over the downloaded one.
- The Spain (`L/LE/panels.json`, the SACTA look) and US (`K/panels.json`, the STARS look) skins ship at those
  folders. Both extend Generic and are complete worked examples; another skin can extend them with
  `"extends": "scope:L/LE"` or `"extends": "scope:K"`.

## Minimal example

A skin that keeps Generic and only makes the bars bevelled cells in upper case:

```json
{
  "extends": "generic",
  "tokens": { "case": "upper", "bevel": { "width": 2 } },
  "primitives": {
    "bar_cell": { "states": { "normal": { "box": { "kind": "bevel", "fill": "bar" } } } }
  }
}
```

## Name, author and description

Three optional keys describe the skin to people; the Skin section of the game lists a skin by them:

| Key | Accepts |
|---|---|
| `name` | one line of text, 1 to 40 characters, no space at either end. Without it the game names the skin from its folder, for example `L/LE` |
| `author` | one line of text, 1 to 60 characters |
| `description` | one line of text, 1 to 200 characters |

The file must still set at least one of `extends`, `tokens`, `primitives` or `components`. The Spain and US skins
are named `Spain (SACTA)` and `US (STARS)`. The [skins catalog](skins-catalog.md) (`SKINS/<id>/panels.json`,
picked by the player instead of by airport) requires `name` and `author`.

## Checks and shipping

Every pull request that touches a `panels.json` runs `python tools/validate_skin.py` on every skin (the game's
strict rules, see [the validator](skins-modding.md#the-validator)) and the colour-profile check
(`python tools/color_profiles_manifest.py --validate-only`, also part of the required `validate` check), which
applies the same rules. The release then lists `panels.json` in the colour-profiles manifest for that scope, with
its hash and size, and packs it in the colour-profiles archive that the game downloads. Do not edit the generated
manifest by hand. The `panels` file kind is gated on the `color_profiles.panels` capability
([channel gates](channel-gates.md)); a mode a build does not support makes that build show Generic
([capabilities](skins-modding.md#capabilities)).
