"""A ready-made OpenGameArt catalogue, so a new install does not re-read the site.

Reading every OpenGameArt entry page politely takes about two days. A
maintainer exports what one installation has read with tools/export_seed.py:
public metadata only (titles, tags, authors, licences, previews, file links and
sizes), never anything local such as downloads, notes or moderation. The
manifest ships the export as storage seeds, which Möbius writes into a new
installation's storage; an update only adds seed files that do not exist yet,
so every export goes into its own dated folder.

The sync job imports the newest complete set once. Entries the installation
lacks are added, entries still waiting for their page to be read take the
seed's details, and everything else (fresher reads, entries hidden or
withdrawn here) is left alone. Older seed folders are then removed.
"""
from __future__ import annotations

import gzip
import json
import os
import shutil
import zlib
from collections import Counter
from pathlib import Path

from . import catalog
from .db import dumps, loads, now, transaction
from .sources import opengameart as oga

SCHEMA = 1
INDEX = 'opengameart-index.json'
PART_LIMIT = 3_500_000   # bytes per compressed part; Möbius caps one storage seed at 4 MiB
DESCRIPTION_MAX = 600
STORAGE_DIR = 'catalog/seed'
PACKAGE_DIR = Path(__file__).resolve().parents[1] / 'seed'

# What leaves an installation: the entry as OpenGameArt shows it, nothing local.
FIELDS = ('source_id', 'type', 'extra_types', 'title', 'description', 'tags', 'categories', 'style', 'license',
          'authors', 'source_url', 'thumbnail_url', 'preview_url', 'formats', 'duration', 'popularity',
          'published_at', 'downloads')
ATTRIBUTES = ('slug', 'art_type', 'details', 'page_fetched_at', 'node_id', 'licenses_offered', 'copyright_notice',
              'favorites', 'source_downloads', 'thumb_small', 'previews', 'audio_preview', 'submitter',
              'default_variant', 'listed_at', 'files', 'contents', 'contents_from')


def record(asset: dict) -> dict:
    """The exportable part of one OpenGameArt entry."""
    out = {key: asset.get(key) for key in FIELDS}
    out['description'] = (asset.get('description') or '')[:DESCRIPTION_MAX]
    attributes = asset.get('attributes') or {}
    kept = {key: attributes[key] for key in ATTRIBUTES if attributes.get(key) is not None}
    if isinstance(kept.get('files'), list):
        kept['files'] = kept['files'][:500]
    if isinstance(kept.get('previews'), list):
        kept['previews'] = kept['previews'][:4]
    out['attributes'] = kept
    return out


def _meta(conn, key: str, default):
    row = conn.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
    return loads(row[0], default) if row else default


def export(conn, out_dir: Path, *, generated_at: str | None = None) -> dict:
    """Write the index and compressed parts for every published OpenGameArt entry."""
    rows = conn.execute("SELECT * FROM assets WHERE source=? AND origin='index' AND status='published' "
                        "ORDER BY source_id", (oga.SOURCE,)).fetchall()
    records = [record(catalog.row_dict(row)) for row in rows]
    stamp = generated_at or now()
    state = _meta(conn, 'opengameart_state', {})
    parts = 1
    while True:  # split by a stable hash until every part fits
        buckets: list[list[dict]] = [[] for _ in range(parts)]
        for item in records:
            buckets[zlib.crc32(item['source_id'].encode()) % parts].append(item)
        blobs = [gzip.compress(json.dumps({'schema': SCHEMA, 'part': number, 'records': bucket},
                                          ensure_ascii=False, separators=(',', ':')).encode(), 9, mtime=0)
                 for number, bucket in enumerate(buckets, start=1)]
        if max(len(blob) for blob in blobs) <= PART_LIMIT or parts >= 32:
            break
        parts += 1
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob('opengameart-*'):
        old.unlink()
    names = []
    for number, blob in enumerate(blobs, start=1):
        name = f'opengameart-part{number}.json.gz'
        (out_dir / name).write_bytes(blob)
        names.append(name)
    index = {
        'schema': SCHEMA, 'source': oga.SOURCE, 'generated_at': stamp,
        'listed_at': state.get('full_at') or stamp, 'entries': len(records),
        'read': sum(1 for item in records if item['attributes'].get('details') == 'complete'),
        'kenney_skip': sorted(_meta(conn, 'opengameart_kenney', [])), 'parts': names,
    }
    (out_dir / INDEX).write_text(json.dumps(index, ensure_ascii=False, indent=1) + '\n')
    return {**index, 'bytes': [len(blob) for blob in blobs]}


def tag(index: dict) -> str:
    """The dated folder name a seed lives in once installed, e.g. 20261009T1200Z."""
    return ''.join(ch for ch in index['generated_at'] if ch.isalnum())[:13] + 'Z'


def _index(folder: Path) -> dict | None:
    try:
        index = json.loads((folder / INDEX).read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(index, dict) or index.get('schema') != SCHEMA or index.get('source') != oga.SOURCE:
        return None
    parts = index.get('parts')
    if not isinstance(parts, list) or not parts or not all(
            isinstance(name, str) and '/' not in name and (folder / name).is_file() for name in parts):
        return None  # incomplete set
    return index


def _storage_root() -> Path | None:
    root = os.environ.get('APP_STORAGE_DIR')
    return Path(root) / STORAGE_DIR if root else None


def newest() -> tuple[dict, Path] | None:
    """The newest complete seed available: installed storage seeds or the package's own."""
    folders = []
    root = _storage_root()
    if root and root.is_dir():
        folders += [path for path in root.iterdir() if path.is_dir()]
    folders.append(PACKAGE_DIR)
    found = [(index, folder) for folder in folders if (index := _index(folder))]
    return max(found, key=lambda pair: pair[0]['generated_at']) if found else None


def _merge(conn, item: dict) -> str:
    source_id = item.get('source_id')
    if not isinstance(source_id, str):
        return 'invalid'
    asset_id = catalog.asset_id(oga.SOURCE, source_id)
    row = conn.execute("SELECT status, json_extract(attributes, '$.details') AS details FROM assets WHERE id=?",
                       (asset_id,)).fetchone()
    complete = (item.get('attributes') or {}).get('details') == 'complete'
    full = {**item, 'source': oga.SOURCE, 'origin': 'index', 'status': 'published'}
    if row is None:
        catalog.upsert(conn, full)
        if not complete:
            conn.execute('INSERT OR IGNORE INTO crawl_queue (source, source_id, priority, queued_at) '
                         'VALUES (?,?,0,?)', (oga.SOURCE, source_id, now()))
        return 'added'
    if row['status'] != 'published' or row['details'] == 'complete' or not complete:
        return 'kept'  # hidden or withdrawn here, already read here, or nothing better in the seed
    catalog.upsert(conn, full)
    conn.execute('DELETE FROM crawl_queue WHERE source=? AND source_id=?', (oga.SOURCE, source_id))
    return 'filled'


def import_newest(conn, log=print) -> dict | None:
    """Import the newest seed once; returns counts, or None when there is nothing new."""
    found = newest()
    if found is None:
        return None
    index, folder = found
    key = f'{index["generated_at"]}:{index["entries"]}'
    if _meta(conn, 'opengameart_seed', None) == key:
        return None
    counts: Counter = Counter()
    for name in index['parts']:
        try:
            data = json.loads(gzip.decompress((folder / name).read_bytes()))
        except (OSError, ValueError, EOFError) as exc:
            log(f'OpenGameArt seed {name} could not be read ({exc}); skipped this seed.')
            return None
        with transaction(conn):
            for item in data.get('records') or []:
                try:
                    counts[_merge(conn, item)] += 1
                except catalog.Invalid:
                    counts['invalid'] += 1
    with transaction(conn):
        if not _meta(conn, 'opengameart_kenney', None) and index.get('kenney_skip'):
            conn.execute("INSERT INTO meta (key, value) VALUES ('opengameart_kenney', ?) "
                         "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (dumps(index['kenney_skip']),))
        state = _meta(conn, 'opengameart_state', {})
        if not state.get('full_at'):  # listed when the seed was made: only newer entries need listing
            state.update(full_at=index['listed_at'], new_at=index['generated_at'])
            conn.execute("INSERT INTO meta (key, value) VALUES ('opengameart_state', ?) "
                         "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (dumps(state),))
        conn.execute("INSERT INTO meta (key, value) VALUES ('opengameart_seed', ?) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (dumps(key),))
    root = _storage_root()
    if root and root.is_dir():
        for other in root.iterdir():
            if other.is_dir() and other != folder:
                shutil.rmtree(other, ignore_errors=True)
    log(f'OpenGameArt seed {index["generated_at"]}: ' + ', '.join(f'{k} {v}' for k, v in sorted(counts.items())))
    return dict(counts)
