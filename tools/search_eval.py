#!/usr/bin/env python3
"""Search quality check: realistic queries against the live library.

    APP_STORAGE_DIR=/data/apps/<id> python3 tools/search_eval.py [--show]

Each case states what a good top five looks like. A case passes when at least
`min` of the top `k` results mention one of the expected words (title, tags,
pack contents) or match an expected id, and, when given, have the expected
type. Sounds come live from Freesound and are not part of this offline-ish
check. Exit status is the number of failing cases.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from commons import catalog, db, search  # noqa: E402

CASES = [
    # (query, expected words or ids, min matches in top k, k, expected type or None)
    ('grass texture', ['grass'], 4, 5, 'texture'),
    ('mossy rock texture, cc0, 2k', ['moss', 'rock'], 4, 5, 'texture'),
    ('brick wall 2k', ['brick'], 4, 5, 'texture'),
    ('rusty metal', ['rust'], 4, 5, None),
    ('cobblestone', ['cobble'], 3, 5, None),
    ('road texture', ['road', 'asphalt'], 3, 5, 'texture'),
    ('tree bark', ['bark'], 4, 5, None),
    ('lava', ['lava'], 2, 5, None),
    ('night sky hdri', ['night', 'moon'], 3, 5, 'hdri'),
    ('snowy hdri', ['snow'], 3, 5, 'hdri'),
    ('forest hdri', ['forest', 'wood', 'tree'], 3, 5, 'hdri'),
    ('wooden chair', ['chair'], 4, 5, None),
    ('wooden crate', ['crate'], 2, 5, None),
    ('barrel', ['barrel'], 2, 5, None),
    ('low poly tree', ['tree', 'nature', 'forest'], 3, 5, None),
    ('low-poly animated character', ['character', 'man', 'woman', 'knight', 'people'], 3, 5, None),
    ('zombie', ['zombie'], 1, 3, None),
    ('sci-fi gun', ['gun', 'blaster', 'weapon', 'rifle', 'pistol'], 2, 5, None),
    ('sword', ['sword', 'weapon'], 2, 5, None),
    ('fantasy castle', ['castle'], 2, 5, None),
    ('medieval village', ['medieval', 'village'], 2, 5, None),
    ('dungeon', ['dungeon'], 2, 5, None),
    ('car model', ['car', 'vehicle'], 2, 5, None),
    ('spaceship', ['space', 'ship'], 2, 5, None),
    ('furniture', ['furniture', 'chair', 'table', 'sofa'], 3, 5, None),
    ('kitchen props', ['kitchen', 'food', 'cook'], 2, 5, None),
    ('low-poly animals', ['animal', 'farm', 'pet'], 2, 5, None),
    ('marble track', ['marble'], 1, 5, None),
    ('racing track', ['racing', 'race', 'track'], 1, 5, None),
    ('tent', ['tent'], 1, 5, None),
    ('coin pickup', ['coin'], 1, 5, None),
    ('pixel art platformer', ['platformer', 'pixel'], 3, 5, 'sprite'),
    ('ui buttons', ['ui', 'button', 'interface'], 3, 5, 'ui'),
    ('crosshair', ['crosshair'], 1, 3, None),
    ('font', ['font'], 1, 3, None),
    ('skybox', ['sky'], 3, 5, None),
    ('stylized nature', ['nature', 'stylized'], 2, 5, None),
    # Objects that mostly live inside packs, and words that used to mislead
    ('campfire', ['campfire', 'fire', 'camp'], 1, 5, 'model'),
    ('bow and arrow', ['bow', 'arrow'], 2, 5, None),
    ('dog', ['dog', 'animal', 'pet'], 2, 3, None),
    ('potion', ['potion'], 2, 5, None),
    ('ladder', ['ladder'], 2, 5, None),
    ('fence model', ['fence'], 2, 5, 'model'),
    ('treasure chest', ['chest', 'treasure'], 2, 5, None),
    ('spaceship', ['space', 'ship', 'rocket'], 3, 5, None),
    ('animated dragon', ['dragon'], 1, 5, None),
    # Music and community 2D art (OpenGameArt; fuller once its entry pages are read)
    ('calm loopable music', ['calm', 'peace', 'relax', 'loop', 'ambient', 'gentle', 'soft'], 3, 5, 'music'),
    ('8-bit battle music', ['chip', '8-bit', '8 bit', '8bit', 'battle', 'boss', 'fight', 'retro', 'nes'], 3, 5, 'music'),
    ('epic orchestral music', ['epic', 'orchestra', 'cinematic'], 3, 5, 'music'),
    ('creepy horror music', ['horror', 'creepy', 'spooky', 'scary', 'dark'], 3, 5, 'music'),
    ('victory jingle', ['victory', 'jingle', 'win', 'fanfare'], 2, 5, None),
    ('pixel art dungeon tileset', ['dungeon', 'tile'], 3, 5, None),
    ('explosion sprite sheet', ['explosion', 'explode', 'blast'], 3, 5, None),
    ('rpg item icons', ['icon', 'item'], 3, 5, None),
    ('laser sound effect', ['laser'], 2, 5, None),
]


def text_of(asset: dict) -> str:
    attributes = asset.get('attributes') or {}
    return ' '.join([asset['id'], asset['title'], ' '.join(asset.get('tags') or []), asset.get('description') or '',
                     ' '.join(attributes.get('contents') or [])]).lower()


def run(conn, show: bool = False) -> int:
    failures = 0
    for query, expected, need, k, kind in CASES:
        result = search.search(conn, query, limit=k)
        top = [catalog.get(conn, r['id']) for r in result['results'][:k]]
        good = sum(1 for asset in top if any(word in text_of(asset) for word in expected)
                   and (kind is None or kind == asset['type'] or kind in (asset.get('extra_types') or [])))
        ok = good >= need
        failures += not ok
        print(f'{"PASS" if ok else "FAIL"} {good}/{k} (need {need})  {query!r}  total={result["total"]}')
        if show or not ok:
            for asset in top:
                print(f'       {asset["id"]:<48} {asset["type"]:<9} {asset["title"][:50]}')
    print(f'\n{len(CASES) - failures}/{len(CASES)} cases pass')
    return failures


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--show', action='store_true', help='print the top results of passing cases too')
    parser.add_argument('--db', help='database path (default: the app storage catalogue)')
    args = parser.parse_args()
    raise SystemExit(run(db.connect(args.db), args.show))
