#!/usr/bin/env python3
"""Copy the Asset Commons package from this project to /data/apps/asset-commons.

The project folder is the authoring source; Möbius applies installed apps from
/data/apps/<slug>. This copies exactly the files the manifest declares (entry,
icon, source_files) and removes stale declared-package files that were dropped,
then the agent runs the apply step. It never touches the app's data directory.

    python3 tools/install_local.py [--dest /data/apps/asset-commons]
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def package_files(manifest: dict) -> list[str]:
    files = [manifest['entry'], 'mobius.json', manifest.get('icon'), (manifest.get('schedule') or {}).get('job')]
    files += manifest.get('source_files') or []
    # Storage seeds (the ready-made catalogue) and Store listing media under static/store/ are
    # tracked package files too, though not source_files.
    files += [value for value in (manifest.get('storage_seeds') or {}).values() if isinstance(value, str)]
    store = manifest.get('store') or {}
    files += [store.get('hero')] + [shot.get('src') for shot in store.get('screenshots') or []]
    return sorted({f for f in files if f})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--dest', default='/data/apps/asset-commons')
    args = parser.parse_args()
    manifest = json.loads((ROOT / 'mobius.json').read_text())
    dest = Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)
    wanted = package_files(manifest)
    for name in wanted:
        source = ROOT / name
        if not source.is_file():
            raise SystemExit(f'Declared file is missing: {name}')
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    # The installed app's .gitignore is managed by Möbius (it decides what is source and what may be
    # published, e.g. admitting static/store/ listing media); never overwrite it with the project's.
    # Drop package files from earlier copies that the manifest no longer declares.
    keep = set(wanted) | {'.gitignore'}
    for path in dest.rglob('*'):
        relative = path.relative_to(dest).as_posix()
        if path.is_file() and not relative.startswith('.git/') and relative not in keep \
                and path.suffix in ('.py', '.js', '.jsx', '.md', '.json', '.png', '.gz', '.html'):
            path.unlink()
            print(f'removed stale {relative}')
    print(f'copied {len(wanted)} files to {dest}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
