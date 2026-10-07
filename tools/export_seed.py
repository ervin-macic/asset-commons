#!/usr/bin/env python3
"""Export the ready-made OpenGameArt catalogue that new installs start from.

    APP_STORAGE_DIR=/data/apps/<id> python3 tools/export_seed.py
    python3 tools/export_seed.py --db /path/to/commons.sqlite3

Writes seed/opengameart-index.json and seed/opengameart-partN.json.gz (each
part under Möbius's 4 MiB storage-seed limit) from a library that has read
OpenGameArt, then points mobius.json's storage_seeds at them under a new dated
folder, so installs and updates pick the new export up. Only public
OpenGameArt metadata is exported (see commons/seed.py); review the summary
before publishing.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from commons import db, seed  # noqa: E402


def point_manifest(manifest_path: Path, index: dict) -> dict:
    manifest = json.loads(manifest_path.read_text())
    seeds = {key: value for key, value in (manifest.get('storage_seeds') or {}).items()
             if not key.startswith(seed.STORAGE_DIR + '/')}
    folder = f'{seed.STORAGE_DIR}/{seed.tag(index)}'
    for name in [seed.INDEX, *index['parts']]:
        seeds[f'{folder}/{name}'] = f'seed/{name}'
    manifest['storage_seeds'] = seeds
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return seeds


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--db', help='catalogue database (default: the app storage catalogue)')
    parser.add_argument('--out', default=str(ROOT / 'seed'), help='output folder (default: seed/)')
    parser.add_argument('--manifest', default=str(ROOT / 'mobius.json'), help='manifest to update')
    args = parser.parse_args()
    conn = db.connect(args.db)
    index = seed.export(conn, Path(args.out))
    seeds = point_manifest(Path(args.manifest), index)
    total = sum(index['bytes'])
    print(f'{index["entries"]:,} entries ({index["read"]:,} with full details) in {len(index["parts"])} parts, '
          f'{total / 1e6:.1f} MB: ' + ', '.join(f'{b / 1e6:.2f} MB' for b in index['bytes']))
    print(f'storage_seeds now: {len(seeds)} files under {seed.STORAGE_DIR}/{seed.tag(index)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
