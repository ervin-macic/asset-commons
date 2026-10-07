# Asset Commons

*Shared resources for agents and humans.* A Möbius community app: a communal
library of free, openly licensed creative assets — PBR textures, HDRI skies,
3D models, sounds, music, animations, 2D art and UI kits — that people browse and every agent on the
instance can search, download and credit through native tools.

## Install

In Möbius, open the App Store and find Asset Commons under **From the
community**, or use **From URL** with this repository's `mobius.json`:
`https://raw.githubusercontent.com/ervin-macic/asset-commons/main/mobius.json`.
On first run it imports the ready-made OpenGameArt catalogue and indexes the
other sources (a few minutes). Connecting a free Freesound API key in
**Sources** adds live CC0 sound search; nothing else needs setting up.

## What it does today (v0.6)

- **Library** of ~5,000 CC0 assets indexed from [Poly Haven](https://polyhaven.com)
  and [ambientCG](https://ambientcg.com): metadata, previews and exact download
  listings. Asset files are not mirrored; they are fetched one at a time when
  someone downloads them.
- **CC0 sounds from [Freesound](https://freesound.org), searched live** once the
  owner connects a free Freesound API key in the app (Sources). The key is saved
  from the app frame straight into Möbius's encrypted per-app store; only the
  app's service reads it. Freesound's API terms forbid copying its database, so
  searches are cached for an hour and a sound is kept only after it is
  downloaded (for credits). Downloads are the high-quality OGG/MP3 previews;
  originals need a Freesound login.
- **Game packs from [Kenney](https://kenney.nl/assets) and
  [Quaternius](https://quaternius.com)** (about 300, all CC0): low-poly 3D,
  animated characters, 2D sprites, UI kits and audio, one entry per pack, read
  from their websites politely (paced requests, pack pages revisited at most
  monthly). Kenney packs download as Kenney's own zips; Quaternius packs are
  free on itch.io behind a pay-what-you-want checkout, which Asset Commons does
  not automate, so they link out.
- **[OpenGameArt](https://opengameart.org) CC0 entries** (about 17,000: 2D
  sprites and tilesets, music, 3D models, textures, sound effects). There is no
  API, so the site is read the way a visitor would, within its robots.txt (ten
  seconds between requests): a monthly listing pass (about 120 pages) makes
  every entry searchable by title, a daily pass picks up new ones, and entry
  pages (author, tags, licences, exact files) are read through a queue, most
  favourited first — about two days for the first full pass, after which only
  new entries are read. Opening an entry an agent needs reads its page at
  once. Kenney's uploads there are skipped (indexed from kenney.nl). Licences
  are as declared by each uploader.
- **Music** as its own type (OpenGameArt tracks, Kenney's music packs), with
  mood and genre words understood ("calm loopable music", "8-bit battle music").
- **What's inside packs**: each Kenney pack's file list is read from the zip's
  own index with one small range request, so single items are searchable
  ("campfire" → Survival Kit) and agents can `pick` just those files.
- **Tools directory**: generators (3D, sound, music, images), other free
  libraries and helper tools, each with how an agent can use it, pricing and
  the licence of its outputs. Searches suggest tools when the library lacks
  something; agents add links and field notes, the owner verifies or hides.
- **Search** in plain words with filters understood from the text ("mossy rock
  texture, cc0, 2k", "wooden chair under 10k tris"), ranked so results covering
  every concept come first, with a mild preference for public-domain assets.
- **Licences first**: every asset shows its licence; only free licences are
  accepted (no NC/ND/"royalty-free"); credit lines are generated (TASL).
- **Agent tools** (`asset_commons_search`, `_get`, `_download`, `_credits`,
  `_note`, `_add_resource`) plus a short always-on note and the `asset-commons`
  skill. Downloads write
  `asset-commons.json` provenance and `ASSET-LICENSE.txt`; the credits tool
  rebuilds a project's `CREDITS.md` from them.
- **Engine import notes** for Godot 4, three.js, Unity, Unreal and Blender.
- **Background refresh**: a daily job (owner-adjustable) refreshes each source
  when it is due — weekly for the curated sources, daily for new OpenGameArt
  entries — and carries on reading OpenGameArt entry pages.

## Layout

| Path | Role |
|---|---|
| `index.jsx`, `ui/`, `lib/`, `theme.js` | The browse/search interface (opaque app frame; previews via the Möbius proxy) |
| `service.py` | App service: UI routes + agent tools (`POST /tools/<name>`) |
| `commons/` | Catalogue engine: schema, search, licences, credits, import notes, downloads, source importers |
| `sync.py` | Catalogue refresh (also the scheduled job) |
| `asset-commons.md`, `asset-commons-core.md` | Agent skill and always-on prompt note |
| `resources.json`, `commons/resources.py` | Tools directory: curated starter list and storage |
| `tests/` | Offline tests: `python3 -m pytest -q tests` |
| `tools/search_eval.py` | Search quality check against the live library |
| `tools/install_local.py` | Copies the declared package to `/data/apps/asset-commons` for `apply_app` |
| `seed/`, `commons/seed.py`, `tools/export_seed.py` | Ready-made OpenGameArt catalogue for new installs, and its export |
| `static/store/` | Store listing screenshots (the listing text lives in `mobius.json` → `store`) |

Data lives in the app's storage directory (`catalog/commons.sqlite3`, WAL mode).

## The ready-made catalogue

Reading every OpenGameArt entry page takes about two days at the ten seconds
between requests its robots.txt asks for, so the package ships what one
installation has read: `seed/opengameart-index.json` and compressed parts
(each under Möbius's 4 MiB storage-seed limit), declared as `storage_seeds`.
Möbius writes them into a new installation's storage; the sync job imports the
newest set once, adding missing entries and filling ones whose pages are still
unread, and never overriding what the installation has read or hidden itself.
Updates only add seed files that do not exist yet, so each export goes into
its own dated folder.

The export holds public OpenGameArt metadata only — titles, tags, authors,
licences, previews, file links and sizes, descriptions cut to 600 characters —
never downloads, notes, owner moderation or Freesound data. To refresh it for a
release, from a library that has read OpenGameArt:

    APP_STORAGE_DIR=/data/apps/<id> python3 tools/export_seed.py

That rewrites `seed/` and points `mobius.json`'s `storage_seeds` at a new
dated folder; review the printed summary before publishing.

## Roadmap

1. ~~Core data model, search and browse UI~~
2. ~~Agent-facing search and download API~~
3. More sources: ~~Freesound (live, API key)~~, ~~Kenney, Quaternius (packs)~~, ~~OpenGameArt (CC0 entries)~~
4. Community submissions with licence declaration and a moderation queue
5. Collections / starter packs
6. ~~App Store packaging~~ (community listing, ready-made catalogue); cross-instance (federated) sharing

## Credits

Poly Haven assets and previews come from the Poly Haven API; ambientCG assets
and previews from the ambientCG API; sounds from the Freesound API (CC0 sounds
only); Kenney and Quaternius packs from their websites; OpenGameArt entries
from opengameart.org (CC0 entries only, as declared by their uploaders). All of
these are published as CC0.
