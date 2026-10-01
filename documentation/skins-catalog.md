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

This page is about catalog skins. The keys, values and the rule that **a skin changes the look, never the
features** are the ones in [session skins](session-skins-panels-json.md); read that page for the full key table.

## Make one

1. Pick an id: a lowercase slug of letters, digits and single hyphens, at most 40 characters, for example
   `harbour-blue`. `generic` and `realistic` are taken by the game.
2. Create `SKINS/<id>/panels.json`. The easiest start is to copy the Generic skin's keys (the table in
   [session skins](session-skins-panels-json.md) lists every key and its Generic value) and change what you want.
   A skin does not have to set every key: a missing key keeps the Generic value.
3. Add the metadata the picker shows:

   | Key | Required | Rule |
   |---|---|---|
   | `name` | yes | the name in the list, 1 to 40 characters, one line, unique among catalog skins ignoring case |
   | `author` | yes | who made it, 1 to 60 characters, one line |
   | `description` | no | one sentence about the look, up to 280 characters |

   Metadata is text for people. It is never a skin value and the game never applies it.
4. Optionally add `SKINS/<id>/README.md` with notes (what it is based on, credits). It is for reviewers and
   is not shipped to players.

```json
{
  "name": "Harbour Blue",
  "author": "Jane Modder",
  "description": "Cool blue bevelled cells with upper-case chrome.",
  "bar_style": "cells",
  "text_case": "upper",
  "bevel": 2,
  "bar_color": "1F3555",
  "edge_color": "35527D",
  "text_font": "barlow_semi_condensed"
}
```

## What you can and cannot change

- **Colours**: every `*_color` key, plain hex `RRGGBB` or `RRGGBBAA`, without a `#`.
  Players can recolour a skin in game. They cannot change its structure.
- **Fonts**: `text_font` and `data_font`, one of `noto_sans`, `courier_prime`, `barlow_semi_condensed`.
  A skin cannot bring its own font files.
- **Structure**, changed only here, in the repository (a player cannot change these in game):

  | Key | Allowed values |
  |---|---|
  | `frame_style` | `window`, `sacta`, `none` |
  | `bar_style` | `bars`, `cells`, `dcb` |
  | `strip_style` | `dark`, `paper_es`, `paper_us` |
  | `text_case` | `as_written`, `upper` |
  | `bevel` | a whole number from `0` to `8` |

- **Nothing else.** Any other key is rejected, and so is any other file in the folder (only `panels.json` and an
  optional `README.md`). A skin cannot add a feature, rename one, or imitate a field of a real system the game
  does not simulate. A file may not exceed 16 KiB, and must set at least one look key, not only metadata.

## Preview before you submit

Put the skin in a local clone, then check it in two places:

1. `python tools/skins_manifest.py --validate-only` must pass (it is also part of the required `validate` check).
2. Look at it in the game. Open a session and choose your skin in Settings, Skin, then check the top bar, a
   window, a datablock popup and the traffic strip, in both a short and a long callsign list. Text must stay
   readable on every surface it sits on: `text_color` on `panel_color`, `strip_text_color` on `strip_color`,
   `selection_text_color` on `selection_color`, `field_text_color` on `field_color`.

Add one screenshot of the session with the skin to the pull request. Reviewers decide by looking at it.

## Submit

Open a pull request to `main` that adds only your `SKINS/<id>/` folder. Do not edit anything under `.voiceatc/`
(the release writes it), and do not touch the gates: a maintainer decides when the catalog reaches which
game build.

## How it ships (maintainers)

The catalog is published **only** as a v3 dataset: `.voiceatc/v3/skins_manifest.json` and the `skins-full.zip`
release asset, written by `tools/community_release_manifest.py` beside the other v3 datasets. There is no default
manifest, no default zip and no entry in the release manifest, so game builds that predate skins never read it.
`tools/stable_contract_guard.py` fails the release if any of those default paths appears. `.voiceatc/gates.json`
holds a `skins` path gate with the same `min_game_version` as the `panels` kind gate, copied onto each v3 entry;
see [channel gates](channel-gates.md).

Each v3 entry has the skin's `id` (the folder name), `repo_path`, `sha256`, `size_bytes`, `name`, `author` and,
when set, `description`, so the picker can list the catalog without opening the zip.
