"""Asset records: types, validation, storage and the shapes callers see.

`upsert` is the single way assets enter the library (sync jobs today,
submissions later). `card` is the compact search-result shape; `detail` is the
full record with licence, credit line, downloads and import notes.
"""
from __future__ import annotations

import re
import sqlite3

from . import credits, importnotes
from .db import dumps, loads, now, transaction
from .licenses import LICENSES, describe

TYPES = {
    'texture': {'label': 'Textures', 'one': 'Texture', 'blurb': 'PBR materials, decals and surfaces'},
    'model': {'label': 'Models', 'one': 'Model', 'blurb': '3D models, preferably glTF'},
    'hdri': {'label': 'HDRIs', 'one': 'HDRI', 'blurb': 'Skies and image-based lighting'},
    'sound': {'label': 'Sounds', 'one': 'Sound', 'blurb': 'Sound effects and ambience'},
    'music': {'label': 'Music', 'one': 'Music', 'blurb': 'Soundtracks, loops and jingles'},
    'animation': {'label': 'Animations', 'one': 'Animation', 'blurb': 'Character and object animation'},
    'sprite': {'label': '2D', 'one': '2D art', 'blurb': 'Sprites, tilesets and 2D game art'},
    'ui': {'label': 'UI', 'one': 'UI kit', 'blurb': 'Interface kits, icons, cursors and fonts'},
}
STYLES = ('realistic', 'stylized', 'low-poly', 'pixel', 'toon', 'hand-painted')
STATUSES = ('published', 'pending', 'rejected', 'hidden')
ORIGINS = ('index', 'submission', 'upload', 'federated', 'live')

_ID_PART = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._~-]{0,159}$')
_JSON_FIELDS = ('tags', 'categories', 'authors', 'formats', 'resolutions', 'dimensions', 'attributes',
                'downloads', 'submitted_by', 'extra_types')
_COLUMNS = ('id', 'source', 'source_id', 'type', 'title', 'description', 'tags', 'categories', 'style',
            'license', 'authors', 'source_url', 'thumbnail_url', 'preview_url', 'formats', 'resolutions',
            'max_resolution', 'polycount', 'dimensions', 'duration', 'attributes', 'downloads',
            'downloads_fetched_at', 'popularity', 'published_at', 'status', 'origin', 'submitted_by',
            'extra_types')


class Invalid(ValueError):
    """A record that cannot enter the library, with a human-readable reason."""


def asset_id(source: str, source_id: str) -> str:
    return f'{source}:{source_id}'


def _clean_list(values, limit=64, item_limit=80) -> list[str]:
    seen, out = set(), []
    for value in values or []:
        if not isinstance(value, str):
            continue
        text = re.sub(r'\s+', ' ', value).strip()[:item_limit]
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            out.append(text)
        if len(out) >= limit:
            break
    return out


def normalize(record: dict) -> dict:
    """Validate one incoming record and fill defaults. Raises Invalid."""
    if not isinstance(record, dict):
        raise Invalid('An asset must be an object.')
    source, source_id = record.get('source'), record.get('source_id')
    if not (isinstance(source, str) and re.fullmatch(r'[a-z][a-z0-9-]{1,31}', source)):
        raise Invalid('source must be a short lowercase id.')
    if not (isinstance(source_id, str) and _ID_PART.fullmatch(source_id)):
        raise Invalid('source_id must be 1-160 URL-safe characters.')
    kind = record.get('type')
    if kind not in TYPES:
        raise Invalid(f'type must be one of {", ".join(TYPES)}.')
    # An asset can serve more than one role (an animated character pack is a
    # model and an animation); extra types make it appear under each tab.
    extra_types = [t for t in dict.fromkeys(record.get('extra_types') or []) if t in TYPES and t != kind]
    title = re.sub(r'\s+', ' ', str(record.get('title') or '')).strip()
    if not title:
        raise Invalid('title is required.')
    license_id = record.get('license')
    if license_id not in LICENSES:
        raise Invalid('license must be a recognised free licence id.')
    style = record.get('style')
    if style is not None and style not in STYLES:
        raise Invalid(f'style must be one of {", ".join(STYLES)}.')
    status = record.get('status', 'published')
    if status not in STATUSES:
        raise Invalid('invalid status.')
    origin = record.get('origin', 'index')
    if origin not in ORIGINS:
        raise Invalid('invalid origin.')
    authors = []
    for author in record.get('authors') or []:
        if isinstance(author, dict) and isinstance(author.get('name'), str) and author['name'].strip():
            url = author.get('url') if isinstance(author.get('url'), str) else None
            authors.append({'name': author['name'].strip()[:120], 'url': url})
    clean = {
        'id': asset_id(source, source_id), 'source': source, 'source_id': source_id, 'type': kind,
        'title': title[:160], 'description': str(record.get('description') or '').strip()[:4000],
        'tags': _clean_list(record.get('tags')), 'categories': _clean_list(record.get('categories'), 16),
        'style': style, 'license': license_id, 'authors': authors[:12],
        'source_url': record.get('source_url'), 'thumbnail_url': record.get('thumbnail_url'),
        'preview_url': record.get('preview_url'),
        'formats': _clean_list(record.get('formats'), 24, 16),
        'resolutions': _clean_list(record.get('resolutions'), 16, 8),
        'max_resolution': _int(record.get('max_resolution')), 'polycount': _int(record.get('polycount')),
        'dimensions': _dims(record.get('dimensions')), 'duration': _float(record.get('duration')),
        'attributes': record.get('attributes') if isinstance(record.get('attributes'), dict) else {},
        'downloads': record.get('downloads') if isinstance(record.get('downloads'), list) else None,
        'downloads_fetched_at': now() if isinstance(record.get('downloads'), list) else None,
        'popularity': max(0.0, min(1.0, _float(record.get('popularity')) or 0.0)),
        'published_at': record.get('published_at'), 'status': status, 'origin': origin,
        'submitted_by': record.get('submitted_by') if isinstance(record.get('submitted_by'), dict) else None,
        'extra_types': extra_types,
    }
    for key in ('source_url', 'thumbnail_url', 'preview_url'):
        value = clean[key]
        if value is not None and not (isinstance(value, str) and re.match(r'https://', value)):
            raise Invalid(f'{key} must be an https URL.')
    return clean


def _int(value):
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _float(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and number >= 0 else None  # drop NaN


def _dims(value):
    if isinstance(value, (list, tuple)) and 2 <= len(value) <= 3:
        numbers = [_float(item) for item in value]
        if all(item is not None for item in numbers):
            return [round(item, 4) for item in numbers]
    return None


def _fts_values(clean: dict) -> tuple:
    names = ' '.join(a['name'] for a in clean['authors'])
    contents = ' '.join((clean.get('attributes') or {}).get('contents') or [])
    return (clean['title'], ' '.join(clean['tags']), ' '.join(clean['categories']),
            clean['description'], names, credits.SOURCE_NAMES.get(clean['source'], clean['source']), contents)


def upsert(db: sqlite3.Connection, record: dict, *, keep_status: bool = True) -> str:
    """Insert or update one asset; returns 'inserted' or 'updated'.

    Re-syncing an indexed source never resurrects an asset the owner hid or
    rejected, and keeps download listings that were fetched lazily.
    """
    clean = normalize(record)
    stamp = now()
    existing = db.execute('SELECT rowid, status, downloads, downloads_fetched_at FROM assets WHERE id=?',
                          (clean['id'],)).fetchone()
    values = {key: (dumps(clean[key]) if key in _JSON_FIELDS and clean[key] is not None else clean[key])
              for key in _COLUMNS}
    if existing is None:
        db.execute(f'INSERT INTO assets ({", ".join(_COLUMNS)}, created_at, updated_at) '
                   f'VALUES ({", ".join("?" for _ in _COLUMNS)}, ?, ?)',
                   (*values.values(), stamp, stamp))
        rowid = db.execute('SELECT rowid FROM assets WHERE id=?', (clean['id'],)).fetchone()[0]
        outcome = 'inserted'
    else:
        rowid = existing['rowid']
        if keep_status and existing['status'] in ('hidden', 'rejected'):
            values['status'] = existing['status']
        if values['downloads'] is None:
            values['downloads'] = existing['downloads']
            values['downloads_fetched_at'] = existing['downloads_fetched_at']
        assignments = ', '.join(f'{key}=?' for key in _COLUMNS if key != 'id')
        db.execute(f'UPDATE assets SET {assignments}, updated_at=? WHERE id=?',
                   (*(values[key] for key in _COLUMNS if key != 'id'), stamp, clean['id']))
        db.execute('DELETE FROM assets_fts WHERE rowid=?', (rowid,))
        outcome = 'updated'
    db.execute('INSERT INTO assets_fts (rowid, title, tags, categories, description, authors, source, contents) '
               'VALUES (?, ?, ?, ?, ?, ?, ?, ?)', (rowid, *_fts_values(clean)))
    return outcome


def set_downloads(db: sqlite3.Connection, asset: str, downloads: list) -> None:
    with transaction(db):
        db.execute('UPDATE assets SET downloads=?, downloads_fetched_at=? WHERE id=?',
                   (dumps(downloads), now(), asset))


def row_dict(row: sqlite3.Row) -> dict:
    data = dict(row)
    for key in _JSON_FIELDS:
        if key in data:
            data[key] = loads(data[key], None if key in ('dimensions', 'downloads', 'submitted_by') else
                              ({} if key == 'attributes' else []))
    data.pop('rowid', None)
    return data


def get(db: sqlite3.Connection, asset: str) -> dict | None:
    row = db.execute('SELECT * FROM assets WHERE id=?', (asset,)).fetchone()
    return row_dict(row) if row else None


def _resolution_label(pixels):
    if not pixels:
        return None
    return f'{max(1, round(pixels / 1024))}K'


def _meters(values):
    return ' × '.join(f'{v:.2f}'.rstrip('0').rstrip('.') for v in values) + ' m'


def specs(asset: dict) -> str:
    """A short human summary of what the asset is, for cards and agents."""
    parts = []
    kind = asset['type']
    attributes = asset.get('attributes') or {}
    if kind == 'model':
        if asset.get('polycount'):
            count = asset['polycount']
            parts.append(f'{count / 1e6:.1f}M polys' if count >= 1e6 else
                         f'{count / 1000:.1f}k polys' if count >= 1000 else f'{count} polys')
        if asset.get('dimensions'):
            parts.append(_meters(asset['dimensions']))
    elif kind == 'texture':
        if attributes.get('maps'):
            parts.append('PBR' if len(attributes['maps']) > 1 else attributes['maps'][0])
        if asset.get('max_resolution'):
            parts.append(f'up to {_resolution_label(asset["max_resolution"])}')
        if attributes.get('real_size_m'):
            parts.append(_meters(attributes['real_size_m']))
    elif kind == 'hdri':
        if asset.get('max_resolution'):
            parts.append(f'up to {_resolution_label(asset["max_resolution"])}')
        if attributes.get('lighting'):
            parts.append(attributes['lighting'])
    if attributes.get('pack'):
        items = attributes.get('items')
        parts.append(f'Pack · {items} {attributes.get("item_label") or "files"}' if items else 'Pack')
        if 'animation' in (asset.get('extra_types') or []) or kind == 'animation':
            parts.append('animated')
    elif kind in ('sound', 'music', 'animation'):
        if asset.get('duration'):
            seconds = asset['duration']
            parts.append(f'{int(seconds // 60)}:{int(seconds % 60):02d} min' if seconds >= 60 else f'{seconds:.1f} s')
        if attributes.get('items'):
            parts.append(f'{attributes["items"]} files')
    if asset.get('formats'):
        parts.append(' / '.join(f.upper() for f in asset['formats'][:3]))
    return ' · '.join(parts)


def card(asset: dict) -> dict:
    """The compact search-result shape (shared by the UI and agent tools)."""
    lic = describe(asset['license'])
    return {
        'id': asset['id'], 'title': asset['title'], 'type': asset['type'],
        'license': asset['license'], 'license_short': lic['short'], 'license_tier': lic['tier'],
        'attribution_required': lic['attribution_required'],
        'source': asset['source'], 'source_name': credits.SOURCE_NAMES.get(asset['source'], asset['source']),
        'author': credits.author_names(asset), 'tags': (asset.get('tags') or [])[:8],
        'style': asset.get('style'), 'specs': specs(asset),
        'polycount': asset.get('polycount'), 'max_resolution': asset.get('max_resolution'),
        'duration': asset.get('duration'), 'formats': asset.get('formats') or [],
        'thumbnail_url': asset.get('thumbnail_url'), 'source_url': asset.get('source_url'),
        'thumbnail_fallback': (asset.get('attributes') or {}).get('thumb_small'),
        'preview_url': asset.get('preview_url'),
        'preview_small': (asset.get('attributes') or {}).get('preview_lq'),
        'extra_types': asset.get('extra_types') or [],
        'pack_items': (asset.get('attributes') or {}).get('items') if (asset.get('attributes') or {}).get('pack') else None,
        'pack_label': (asset.get('attributes') or {}).get('item_label'),
        'is_pack': bool((asset.get('attributes') or {}).get('pack')),
        'manual_download': (asset.get('attributes') or {}).get('manual_download'),
        'status': asset.get('status'),
    }


def detail(db: sqlite3.Connection, asset: dict, *, engine: str | None = None) -> dict:
    """The full record: card + description, licence, credit, downloads, import notes."""
    pulls = db.execute('SELECT COUNT(*) FROM pulls WHERE asset_id=?', (asset['id'],)).fetchone()[0]
    data = card(asset)
    data.update({
        'description': asset.get('description') or '',
        'categories': asset.get('categories') or [],
        'tags': asset.get('tags') or [],
        'authors': asset.get('authors') or [],
        'license_detail': describe(asset['license']),
        'credit': credits.credit_line(asset),
        'dimensions_m': asset.get('dimensions'),
        'resolutions': asset.get('resolutions') or [],
        'attributes': asset.get('attributes') or {},
        'preview_url': asset.get('preview_url'),
        'downloads': [_variant_summary(v) for v in asset.get('downloads') or []],
        'downloads_known': asset.get('downloads') is not None,
        'import_notes': importnotes.notes(asset, engine),
        'source_notes': importnotes.source_notes(asset),
        'published_at': asset.get('published_at'),
        'origin': asset.get('origin'),
        'pulls': pulls,
    })
    return data


def _variant_summary(variant: dict) -> dict:
    files = variant.get('files') or []
    return {
        'id': variant.get('id'), 'label': variant.get('label'), 'resolution': variant.get('resolution'),
        'format': variant.get('format'), 'archive': variant.get('archive'),
        'size': variant.get('size') or sum(f.get('size') or 0 for f in files),
        'files': [{'path': f.get('path'), 'url': f.get('url'), 'size': f.get('size')} for f in files],
    }


def related(db: sqlite3.Connection, asset: dict, limit: int = 8) -> list[dict]:
    """Assets of the same type that share the most tags."""
    tags = [t for t in (asset.get('tags') or [])[:6] if re.fullmatch(r'[\w -]{2,40}', t)]
    if not tags:
        return []
    query = ' OR '.join('"' + t.replace('"', '') + '"' for t in tags)
    rows = db.execute(
        'SELECT a.* FROM assets_fts f JOIN assets a ON a.rowid = f.rowid '
        'WHERE assets_fts MATCH ? AND a.id != ? AND a.type = ? AND a.status = \'published\' '
        'ORDER BY bm25(assets_fts, 2.0, 4.0, 1.0, 0.2, 0.2, 0.1, 0.5) LIMIT ?',
        ('{tags categories} : (' + query + ')', asset['id'], asset['type'], limit)).fetchall()
    return [card(row_dict(row)) for row in rows]


def stats(db: sqlite3.Connection) -> dict:
    by_type = {row[0]: row[1] for row in db.execute(
        "SELECT type, COUNT(*) FROM assets WHERE status='published' AND origin != 'live' GROUP BY type")}
    by_source = {row[0]: row[1] for row in db.execute(
        "SELECT source, COUNT(*) FROM assets WHERE status='published' AND origin != 'live' GROUP BY source")}
    by_license = {row[0]: row[1] for row in db.execute(
        "SELECT license, COUNT(*) FROM assets WHERE status='published' AND origin != 'live' GROUP BY license")}
    pending = db.execute("SELECT COUNT(*) FROM assets WHERE status='pending'").fetchone()[0]
    pulls = db.execute('SELECT COUNT(*) FROM pulls').fetchone()[0]
    sources = [dict(row) for row in db.execute('SELECT * FROM sources ORDER BY id')]
    return {
        'total': sum(by_type.values()), 'by_type': by_type, 'by_source': by_source,
        'by_license': by_license, 'pending': pending, 'pulls': pulls, 'sources': sources,
        'types': TYPES,
    }
