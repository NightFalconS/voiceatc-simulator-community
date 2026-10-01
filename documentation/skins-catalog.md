# The skins catalog: make and submit a skin

> Reference for modders. It is written to move into the
> [modding wiki](https://github.com/lainoa-software/voiceatc-simulator-community/wiki) as it stands.

A **skin** changes how the session interface looks: the bars across the screen, the panels, the datablock
popups and the traffic strip. Skins reach players in two ways:

- A **regional skin** is a `panels.json` beside a `colors.json` (see
  [session skins](session-skins-panels-json.md)). The airports under that folder use it by default, so the
  community decides how each airport looks.
- A **catalog skin** is not tied to a place. It lives in `SKINS/<id>/panels.json` and a player picks it in
  Settings, Skin, either for every airport or for one airport.

This page is about catalog skins. How a `panels.json` is written (tokens, primitives, components, `extends`) and
the rule that **a skin changes the look, never the features** are in the [skins modding guide](skins-modding.md);
every key is in the [skin key reference](skins-reference.md).

## Make one

1. Pick an id: a lowercase slug of letters, digits and single hyphens, at most 40 characters, for example
   `harbour-blue`. `generic` and `realistic` are taken by the game.
2. Create `SKINS/<id>/panels.json` with `"extends": "generic"` (or another skin: `scope:L/LE`, `skin:<id>`)
   and write only what you change; everything else keeps the base's value. The
   [cookbook](skins-modding.md#cookbook) has small starting points.
3. Add the metadata the picker shows:

   | Key | Required | Rule |
   |---|---|---|
   | `name` | yes | the name in the list, 1 to 40 characters, one line, unique among catalog skins ignoring case |
   | `author` | yes | who made it, 1 to 60 characters, one line |
   | `description` | no | one sentence about the look, up to 200 characters |

   Metadata is text for people. It is never a skin value and the game never applies it.
4. Optionally add `SKINS/<id>/README.md` with notes (what it is based on, credits). It is for reviewers and
   is not shipped to players.

```json
{
  "name": "Harbour Blue",
  "author": "Jane Modder",
  "description": "Cool blue bevelled cells with upper-case chrome.",
  "extends": "generic",
  "tokens": {
    "colors": { "bar": "1F3555", "edge": "35527D" },
    "fonts": { "text": "barlow_semi_condensed" },
    "case": "upper",
    "bevel": { "width": 2 }
  },
  "primitives": {
    "bar_cell": { "states": { "normal": { "box": { "kind": "bevel", "fill": "bar" } } } }
  }
}
```

## What you can and cannot change

- **Tokens**: colour roles (plain hex `RRGGBB` or `RRGGBBAA`, without a `#`; a skin may add its own roles),
  font roles (`noto_sans`, `courier_prime`, `barlow_semi_condensed`; no font files), type sizes, case and bevel.
  Players can recolour any role in game. They cannot change the structure.
- **Primitives and components**: how each control is drawn and which layout mode each part of the screen uses,
  with every feature placed exactly once ([slots and parity](skins-modding.md#slots-and-parity)).
- **Nothing else.** An unknown key is rejected with a "did you mean" hint, and so is any other file in the folder
  (only `panels.json` and an optional `README.md`). A skin cannot add a feature, rename one, or imitate a field of
  a real system the game does not simulate. A file may not exceed 16 KiB, and must set at least one of `extends`,
  `tokens`, `primitives` or `components`, not only metadata.

## Preview before you submit

Put the skin in a local clone, then check it in two places:

1. `python tools/validate_skin.py SKINS/<id>/panels.json` and `python tools/skins_manifest.py --validate-only`
   must pass (both run on the pull request). [Live reload](skins-modding.md#live-reload) shows each save in a
   running session.
2. Look at it in the game. Open a session and choose your skin in Settings, Skin, then check the top bar, a
   window, a datablock popup and the traffic strip, in both a short and a long callsign list. Text must stay
   readable on every surface it sits on: the `text` role on `panel`, `strip_text` on `strip`, `selection_text`
   on `selection`, `field_text` on `field`.

Add one screenshot of the session with the skin to the pull request. Reviewers decide by looking at it.

## Submit

Open a pull request to `main` that adds only your `SKINS/<id>/` folder. Do not edit anything under `.voiceatc/`
(the release writes it), and do not touch the gates: a maintainer decides when the catalog reaches which
game build.

## How it ships (maintainers)

The catalog is published **only** in the full feed: `.voiceatc/full/skins_manifest.json` and the `skins-full.zip`
release asset, written by `tools/community_release_manifest.py` beside the other full-feed datasets. There is no default
manifest, no default zip and no entry in the release manifest, so game builds that predate skins never read it.
`tools/stable_contract_guard.py` fails the release if any of those default paths appears. `.voiceatc/gates.json`
holds a `skins` path gate that requires the `skins.catalog` capability, copied onto each full-feed entry as `requires`;
see [channel gates](channel-gates.md).

Each full-feed entry has the skin's `id` (the folder name), `repo_path`, `sha256`, `size_bytes`, `name`, `author` and,
when set, `description`, so the picker can list the catalog without opening the zip.
