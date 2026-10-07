---
name: asset-commons
description: How to find, pull and credit free assets (textures, HDRIs, models, sounds, music, animations, 2D, UI) from Asset Commons, this instance's shared CC0-first library, and how to find tools that generate what the library lacks. Read before adding art or audio to a game, video or interactive project, before generating an asset, or when a project needs a CREDITS file.
---

# Asset Commons

Asset Commons is a shared library of free, openly licensed assets that every
agent and the owner use. It indexes trusted CC0 sources (Poly Haven and
ambientCG: about 5,000 textures, HDRIs and models; Kenney and Quaternius: about
300 low-poly 3D, 2D, UI and audio packs; OpenGameArt: about 17,000 CC0
community entries — 2D sprites and tilesets, music, 3D models, textures and
sound effects), searches CC0 sounds live on Freesound once the owner connects
a Freesound key in the app, and labels every asset with its licence. Prefer it over generating assets or hunting the web: the files are
production quality, the licence is known, and attribution is generated for you.

## The loop

1. **Search** — `asset_commons_search` with plain words. Filter words are
   understood and echoed back in `interpreted`:
   - type: texture / material / pbr, model / mesh / prop / gltf, hdri / skybox,
     sound / sfx / ambience, music / song / soundtrack / bgm / jingle,
     animation / mocap, 2d / sprite / tileset, ui / icons / font
   - mood and genre words work for music: `calm`, `battle`, `epic`,
     `orchestral`, `horror`, `loopable`; `8-bit` in an audio query means
     chiptune, elsewhere it means pixel art
   - licence: `cc0`, `public domain`, `no attribution`, `cc-by`, `share-alike`
   - style: `low-poly`, `stylized`, `pixel art`, `realistic`
   - numbers: `2k`/`4k`/`8k` (minimum resolution), `under 5k tris`, `under 3 s`
   Explicit parameters (`type`, `license`, `style`, `tags`, `format`,
   `max_polycount`, `min_resolution`) are hard filters. Style and numbers
   inferred from words relax automatically when nothing matches; read
   `notices` to see what was relaxed. Page with `offset` = `next_offset`.
2. **Inspect** — `asset_commons_get` with the id (and `engine` to trim notes).
   It returns the credit line, real-world size, polycount, maps, every
   download variant with sizes, `default_variant`, and direct file URLs for
   that variant.
3. **Pull** — `asset_commons_download` with `id` and an absolute `dest_dir`
   inside the project (for example `<project>/assets/textures`). It writes
   `<dest_dir>/<asset>/…` plus `asset-commons.json` (provenance) and
   `ASSET-LICENSE.txt`, unpacks zips, verifies checksums when the source gives
   them, and refuses anything over `max_mb` (default 300) before fetching.
   Pick the smallest variant that does the job: 1K–2K textures for games, 2K
   HDRIs for lighting, 4K+ only for close-ups or visible skies.
4. **Wire it up** — follow the returned `import_notes` for the engine.
5. **Credit** — `asset_commons_credits` with `dir` set to the project root and
   `write: true` keeps `CREDITS.md` current. CC0 assets need no credit but are
   listed for provenance; attribution licences (CC BY, OGA-BY) must ship their
   credit line; share-alike assets oblige changed versions of the asset to
   keep the same licence. Mention the licence situation to the owner when an
   asset is not CC0.

## Practical notes

- Normal maps: Godot, three.js, Unity and Blender use the OpenGL map
  (`nor_gl` / `NormalGL`); Unreal uses DirectX (`nor_dx` / `NormalDX`).
- Poly Haven textures include a packed `arm` map (AO, Roughness, Metallic in
  R, G, B) that plugs straight into Godot's ORMMaterial3D or Unreal.
- ambientCG material zips include a ready Godot `.tres` material.
- Poly Haven models are real-world scale in metres and come as glTF with
  textures; keep the `.gltf`, `.bin` and `textures/` folder together.
- The owner sees a card for each tool call and can open the asset in the
  Asset Commons app from it.

## Sounds (Freesound, live)

- Sound searches ("footsteps on gravel sound", `type: "sound"`, `max_duration`)
  go live to Freesound, CC0 only. Other searches report Freesound's match count
  under `by_type.sound`; a search that finds nothing else falls back to sounds.
- If a notice says Freesound is not connected, tell the owner to open Asset
  Commons → Sources and connect a free Freesound API key. Never ask for the key
  in chat; the app stores it encrypted and only its own server uses it.
- Downloads are Freesound's high-quality previews (`hq-ogg` default, `hq-mp3`),
  which suit games and video. Originals (WAV/FLAC) need the owner's Freesound
  login; point to the sound's page when lossless audio matters.
- Freesound's API terms forbid copying its catalogue, so Asset Commons keeps a
  sound only after it is downloaded (for credits) and caches searches for an
  hour. Limits are 60 requests a minute and 2,000 a day per key: search
  deliberately rather than paging through everything.

## OpenGameArt (community entries)

- Ids look like `opengameart:<page-name>`. Only entries offered under CC0 are
  indexed; the licence is as declared by the uploader, and `source_notes`
  says when an entry is also offered under other licences or when its author
  asks for credit (optional under CC0, but worth honouring in CREDITS.md).
- OpenGameArt asks for ten seconds between page requests, so on a new
  install entry pages are read in the background over about two days, most
  popular first. Until then an entry is searchable by its title and type;
  `asset_commons_get` and `asset_commons_download` read its page on the spot
  (a few seconds' wait).
- Downloads are the uploader's own files. The default is every file of the
  entry (zips unpacked); for music and sound effects it is a game-ready OGG
  (an original OGG or MP3 when there is one, otherwise OpenGameArt's OGG
  streaming copy rather than a large WAV). Each file is also its own variant,
  named by its file name, and `preview-ogg` / `preview-mp3` exist for audio.
- `asset_commons_get` lists what an entry's zip contains, so `pick` works
  here too. Some 3D entries ship only `.blend` files: Godot imports them when
  Blender is installed; otherwise export glTF from Blender.
- Quality varies more than on curated sources: check the previews (and the
  field notes other agents left) before building a scene around an entry.

## Game packs (Kenney, Quaternius)

- Each pack is one entry (`kenney:<slug>`, `quaternius:<slug>`) with its item
  count, formats and whether it is animated. Animated packs also appear under
  `type: "animation"`; 2D art is `sprite`, interface kits and fonts are `ui`.
- Kenney packs download as Kenney's zip, unpacked into `<dest_dir>/<pack>/`.
  3D packs hold `Models/GLB format`, `Models/FBX format` and `Models/OBJ
  format`, plus `Previews/` with a PNG per model: use the GLB files in Godot
  and three.js, and copy only the models you need into the project.
- Quaternius packs cannot be fetched automatically: Quaternius hands out files
  through itch.io's pay-what-you-want checkout. The download tool answers with
  the itch.io link; ask the owner to download the zip (free) and tell you where
  it is, then continue. Credit them with `asset_commons_credits` by id.
- Kenney and Quaternius ask for no attribution (CC0) but welcome support; the
  credits file lists them anyway.

## Packs: what's inside, and taking one item

- Kenney packs list their contents (from the zip's own index), so searches
  find items inside them: "campfire" finds Survival Kit's campfire pit. Results
  show `matched_items`, and `asset_commons_get` returns `contents`.
- `asset_commons_download` with `pick: ["campfire pit"]` fetches only those
  files with small range requests, plus their `Textures/` folder and the
  licence, keeping one model format per item (GLB first; pass `format` for
  another). Prefer this to unpacking a whole pack into a project.

## When the library has nothing: the tools directory

- Search results carry `tools` when few assets match, or always when the
  query asks to generate/create/make something ("generate a low-poly dragon").
  Open one with `asset_commons_get` (`tool:meshy`): it says what it makes, how
  an agent can use it (API key, hosted or local MCP, web only, open source,
  built into Möbius), pricing, and the licence of its outputs. Read that last
  part carefully: many free tiers are CC BY (credit required), some models are
  non-commercial, and Hunyuan3D's licence excludes the UK, EU and South Korea.
- Paid generators spend the owner's money: propose one, with its cost and
  output terms, and wait for the owner's go-ahead. Never ask for API keys in
  chat; keys belong in the provider's own setup or a Möbius sealed card.
- Codex chats can generate images directly (the `images` skill), which covers
  quick sprites, icons and texture drafts.

## Give back

- `asset_commons_note` on an asset or tool: what worked, what went wrong, or a
  tip (scale fixes, import quirks, prompts that work). One or two factual
  sentences; the next agent sees it when opening the item.
- `asset_commons_add_resource` when you find a useful generator, library or
  helper that is not listed: what it makes, how to use it, pricing, output
  licence. Duplicate links are detected; entries show as unreviewed until the
  owner verifies them.

## Without the tools

Scripts with owner credentials can call the same library over HTTP, e.g.
`mapi "/api/apps/<app-id>/service/search?q=brick%20wall&type=texture"` and
`mapi "/api/apps/<app-id>/service/asset?id=polyhaven:brick_wall_12"`. Find the
app id with the app list. Downloads still go through the tool (or fetch the
returned URLs yourself and keep the credit line).

## What is not there yet

Quaternius packs do not list their contents, and OpenGameArt entries indexed
only by title (while their pages are still being read) show fewer tags. If a search comes back empty, check the tools
it suggests and say so to the owner rather than silently generating a
substitute.
