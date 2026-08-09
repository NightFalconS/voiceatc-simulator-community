# Player-contributed routes

Player-shared origin–destination routes, published by the VoiceATC Simulator
website. They are an **overlay** on top of the generated route tables in
`ROUTES/`: the game prefers a player route for a pair when one exists and falls
back to the generated (`LainoaSoftware`) route otherwise. The generated tables
are never modified by this tree.

## Layout

```
ROUTES/player/current/{ORIGIN[0:2]}/{ORIGIN}_{DEST}.json   subscriber cycle lane
ROUTES/player/default/{ORIGIN[0:2]}/{ORIGIN}_{DEST}.json   offline fallback lane
```

Lanes are data tiers, not AIRAC cycles — files persist across cycle rollover.
One file per origin–destination pair, at most 8 route variants per file:

```json
{
  "schema_version": 1,
  "origin": "LEMH",
  "dest": "LEPA",
  "routes": [
    {
      "id": "a1b2c3d4",
      "route": "LEMH DCT MAMEB DCT LEPA",
      "author": "Display Name",
      "created_at": "2026-08-08T12:00:00Z",
      "creation_airac": "2607"
    }
  ]
}
```

- `id` is the first 8 hex characters of the SHA-256 of the normalized route
  string. It identifies the variant everywhere: website badges, the nightly
  status artifact, and the game's route cache.
- Routes must carry `DCT` bookends (`ORIGIN DCT … DCT DEST`), uppercase
  `A–Z0-9` tokens, no runway designators, at most 400 characters / 60 tokens.
- `LainoaSoftware` is a reserved author name — it marks generated routes and is
  rejected here.

## Single writer

The website is the only writer of this tree. The daily release and the route
regeneration pipeline **never** create, edit, or delete files under
`ROUTES/player/` — they only read it. Manual pull requests are possible but the
website flow is preferred; `python tools/player_routes_manifest.py
--validate-only` must pass.

## Nightly validation and deprecation

The daily release checks every route against the live cycle's route graph and
navigation data. Routes that no longer resolve (a waypoint or airway
disappeared) are marked `deprecated` in `.voiceatc/player_routes_status.json`
and excluded from the published overlay TSVs — the source file here is left
untouched, so a route that validates again in a later cycle returns
automatically. The website shows the per-route status so anyone signed in can
fix or remove stale routes. When the validation databases are unavailable the
previous statuses carry forward and the release still ships.
