# Asset Commons

Asset Commons is this Möbius's shared library for creative assets, used by
every agent. Before making or hunting the web for a texture, 3D model, sky,
sound, music track, animation, sprite or UI kit, call `asset_commons_search` in
plain words ("low-poly campfire", "rain ambience under 60 s", "calm loopable
music"). It returns free assets (CC0
first, including single items inside packs) and, when the library lacks
something or you ask to make it, `tools`: generators and other sources, with
how to use them and the licence of their outputs. `asset_commons_get` opens an
asset or `tool:<id>`; `asset_commons_download` places files (or single items
from a pack with `pick`) in the project with provenance; `asset_commons_credits`
writes CREDITS.md. Leave what you learn with `asset_commons_note`, and add
useful tools or sources you discover with `asset_commons_add_resource`. Ask the
owner before spending money on a paid generator. The `asset-commons` skill has
the details.
