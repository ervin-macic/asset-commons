"""Tools and resources: how to make assets, and where else to find them.

Asset Commons answers two questions for agents: "is there already a free asset
for this?" (the asset library) and "if not, what can make it, and what are the
strings attached?" (this directory). Each entry says what a tool makes, how an
agent can reach it (API, hosted or local MCP, web only, open source, built
into Möbius), its pricing model and, most importantly, the licence terms of
what it produces.

Entries come from the curated starter list (resources.json) or are added by
agents and people; additions are published at once, marked unreviewed, and the
owner can verify or hide them. Field notes ("worked", "problem", "tip") on
assets and tools carry what one agent learned to the next.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit

from .db import dumps, loads, now, transaction

KINDS = {'generator': 'Generator', 'library': 'Asset library', 'tool': 'Tool'}
PRICING = ('free', 'freemium', 'paid', 'included', 'unknown')
OUTCOMES = ('worked', 'problem', 'tip')
STATUSES = ('published', 'hidden')
SEED_FILE = Path(__file__).resolve().parents[1] / 'resources.json'
_JSON = ('makes', 'inputs', 'formats', 'access', 'tags')


class Invalid(ValueError):
    pass


def _slug(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')[:60]


def _list(value, limit=16, size=60) -> list[str]:
    if isinstance(value, str):
        value = [part for part in re.split(r'[,;]', value)]
    out = []
    for item in value or []:
        text = re.sub(r'\s+', ' ', str(item)).strip()[:size]
        if text and text.lower() not in (o.lower() for o in out):
            out.append(text)
    return out[:limit]


def url_key(url: str) -> str:
    parts = urlsplit(url or '')
    return (parts.hostname or '').removeprefix('www.') + parts.path.rstrip('/')


def normalize(record: dict, origin: str) -> dict:
    if not isinstance(record, dict):
        raise Invalid('A resource must be an object.')
    name = re.sub(r'\s+', ' ', str(record.get('name') or '')).strip()[:80]
    url = str(record.get('url') or '').strip()
    if not name:
        raise Invalid('name is required.')
    if not re.match(r'https://[^\s/]+\.[^\s]+', url):
        raise Invalid('url must be a full https:// link.')
    kind = record.get('kind') or 'tool'
    if kind not in KINDS:
        raise Invalid(f'kind must be one of: {", ".join(KINDS)}.')
    pricing = record.get('pricing') or 'unknown'
    if pricing not in PRICING:
        raise Invalid(f'pricing must be one of: {", ".join(PRICING)}.')
    description = str(record.get('description') or '').strip()
    if len(description) < 12:
        raise Invalid('description should say in a sentence what it is and what it is good for.')
    access = record.get('access') if isinstance(record.get('access'), dict) else {}
    access = {str(k)[:24]: (v if isinstance(v, bool) else str(v)[:160]) for k, v in list(access.items())[:8]}
    return {
        'id': _slug(record.get('id') or name), 'name': name, 'url': url, 'kind': kind,
        'makes': [m.lower() for m in _list(record.get('makes'))], 'inputs': _list(record.get('inputs')),
        'formats': [f.lower() for f in _list(record.get('formats'), 12, 12)], 'access': access, 'pricing': pricing,
        'pricing_note': str(record.get('pricing_note') or '').strip()[:300],
        'output_terms': str(record.get('output_terms') or '').strip()[:600],
        'description': description[:800], 'how_to_use': str(record.get('how_to_use') or '').strip()[:1000],
        'tags': [t.lower() for t in _list(record.get('tags'), 20, 40)],
        'docs': record.get('docs') if isinstance(record.get('docs'), str) and record['docs'].startswith('https://') else None,
        'origin': origin,
    }


def _fts(db, rowid: int, clean: dict) -> None:
    db.execute('DELETE FROM resources_fts WHERE rowid=?', (rowid,))
    db.execute('INSERT INTO resources_fts (rowid, name, tags, makes, description, how_to_use) VALUES (?,?,?,?,?,?)',
               (rowid, clean['name'], ' '.join(clean['tags']), ' '.join(clean['makes'] + [clean['kind']]),
                clean['description'] + ' ' + clean['output_terms'], clean['how_to_use']))


def upsert(db: sqlite3.Connection, record: dict, *, origin: str = 'curated', actor: dict | None = None,
           verified: bool = False) -> tuple[str, str]:
    """Add or update one entry inside the caller's transaction; returns (outcome, id).

    Agent and owner additions never overwrite an existing entry with the same
    link: the existing id comes back as 'exists' so the caller can add a note.
    """
    clean = normalize(record, origin)
    key = url_key(clean['url'])
    for row in db.execute('SELECT id, url, origin, status FROM resources'):
        if url_key(row['url']) == key or row['id'] == clean['id']:
            if origin != 'curated' or row['origin'] != 'curated':
                return 'exists', row['id']
            existing = row
            break
    else:
        existing = None
    stamp = now()
    columns = ('name', 'url', 'kind', 'makes', 'inputs', 'formats', 'access', 'pricing', 'pricing_note',
               'output_terms', 'description', 'how_to_use', 'tags', 'origin')
    values = [dumps(clean[c]) if c in _JSON else clean[c] for c in columns]
    if clean.get('docs'):
        values[columns.index('access')] = dumps({**clean['access'], 'docs': clean['docs']})
    if existing is None:
        db.execute(f'INSERT INTO resources (id, {", ".join(columns)}, added_by, verified_at, status, created_at, '
                   f'updated_at) VALUES (?, {", ".join("?" for _ in columns)}, ?, ?, ?, ?, ?)',
                   (clean['id'], *values, dumps(actor or {'kind': origin}), stamp if verified else None,
                    'published', stamp, stamp))
        outcome = 'inserted'
    else:
        db.execute(f'UPDATE resources SET {", ".join(f"{c}=?" for c in columns)}, updated_at=?'
                   + (', verified_at=?' if verified else '') + ' WHERE id=?',
                   (*values, stamp, *([stamp] if verified else []), existing['id']))
        clean['id'] = existing['id']
        outcome = 'updated'
    rowid = db.execute('SELECT rowid FROM resources WHERE id=?', (clean['id'],)).fetchone()[0]
    _fts(db, rowid, clean)
    return outcome, clean['id']


def ensure_seed(db: sqlite3.Connection) -> int:
    """Load or refresh the curated starter list when resources.json changes."""
    if not SEED_FILE.exists():
        return 0
    raw = SEED_FILE.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    row = db.execute("SELECT value FROM meta WHERE key='resources_seed'").fetchone()
    if row and row['value'] == digest:
        return 0
    entries = json.loads(raw).get('resources') or []
    with transaction(db):
        for entry in entries:
            upsert(db, entry, origin='curated', verified=True)
        db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('resources_seed', ?)", (digest,))
    return len(entries)


def _row(row: sqlite3.Row) -> dict:
    data = dict(row)
    for key in _JSON:
        data[key] = loads(data[key], {} if key == 'access' else [])
    data['added_by'] = loads(data.get('added_by'), {})
    data.pop('rowid', None)
    return data


def access_summary(access: dict) -> str:
    labels = []
    if access.get('built_in'):
        labels.append('built into Möbius')
    if access.get('api'):
        labels.append('API')
    mcp = access.get('mcp')
    if mcp:
        labels.append('hosted MCP' if isinstance(mcp, str) and 'hosted' in mcp else 'MCP (local)')
    if access.get('open_source'):
        labels.append('open source')
    if access.get('web'):
        labels.append('web')
    if access.get('desktop'):
        labels.append('desktop app')
    return ', '.join(labels) or 'see link'


def card(item: dict, notes: int = 0) -> dict:
    return {
        'id': f'tool:{item["id"]}', 'name': item['name'], 'kind': item['kind'], 'kind_label': KINDS[item['kind']],
        'makes': item['makes'], 'pricing': item['pricing'], 'access': access_summary(item['access']),
        'summary': item['description'][:220], 'output_terms': item['output_terms'][:240], 'url': item['url'],
        'origin': item['origin'], 'verified': bool(item.get('verified_at')), 'status': item['status'], 'notes': notes,
    }


def _note_counts(db, ids: list[str]) -> dict[str, int]:
    if not ids:
        return {}
    marks = ','.join('?' for _ in ids)
    return {row[0]: row[1] for row in db.execute(
        f'SELECT target, COUNT(*) FROM notes WHERE target IN ({marks}) GROUP BY target', ids)}


def listing(db, *, kind: str | None = None, makes: str | None = None, include_hidden: bool = False) -> list[dict]:
    rows = [_row(r) for r in db.execute('SELECT * FROM resources ORDER BY origin != \'curated\', name')]
    rows = [r for r in rows if (include_hidden or r['status'] == 'published')
            and (not kind or r['kind'] == kind) and (not makes or makes in r['makes'])]
    counts = _note_counts(db, [f'tool:{r["id"]}' for r in rows])
    return [card(r, counts.get(f'tool:{r["id"]}', 0)) for r in rows]


def search(db, groups: list[list[str]], *, makes: list[str] | None = None, limit: int = 3) -> list[dict]:
    """Directory entries matching the query's concepts, best first; `makes` breaks ties."""
    from .search import _fts_expr  # shared query building (stemming, prefixes, synonyms)
    scores: dict[int, float] = {}
    for words in groups:
        for rowid, rank in db.execute(
                'SELECT rowid, bm25(resources_fts, 6.0, 4.0, 4.0, 1.0, 0.5) FROM resources_fts '
                'WHERE resources_fts MATCH ?', (_fts_expr(words),)).fetchall():
            scores[rowid] = scores.get(rowid, 0.0) + 10.0 - rank
    rows = {r['rowid']: _row(r) for r in db.execute("SELECT rowid, * FROM resources WHERE status='published'")}
    wanted = set(makes or [])
    ranked = []
    for rowid, item in rows.items():
        matched = scores.get(rowid, 0.0) > 0
        score = scores.get(rowid, 0.0)
        if wanted & set(item['makes']):
            score += 6.0 if matched else 2.0
        if score > 0:
            ranked.append((score + (1.0 if item.get('verified_at') else 0.0), matched, item))
    ranked.sort(key=lambda entry: -entry[0])
    picked = ranked[:limit]
    counts = _note_counts(db, [f'tool:{i["id"]}' for _, _, i in picked])
    return [{**card(item, counts.get(f'tool:{item["id"]}', 0)), 'matched_words': matched}
            for _, matched, item in picked]


def get(db, resource_id: str) -> dict | None:
    key = resource_id.removeprefix('tool:')
    row = db.execute('SELECT * FROM resources WHERE id=?', (key,)).fetchone()
    if not row:
        return None
    item = _row(row)
    detail = card(item)
    detail.update({
        'inputs': item['inputs'], 'formats': item['formats'], 'access_detail': item['access'],
        'pricing_note': item['pricing_note'], 'output_terms': item['output_terms'], 'description': item['description'],
        'how_to_use': item['how_to_use'], 'tags': item['tags'], 'added_by': item['added_by'],
        'verified_at': item.get('verified_at'), 'created_at': item['created_at'],
        'field_notes': notes_for(db, f'tool:{item["id"]}'),
    })
    return detail


def notes_for(db, target: str, limit: int = 30) -> list[dict]:
    return [{'id': row['id'], 'text': row['text'], 'outcome': row['outcome'], 'at': row['at'],
             'by': (loads(row['actor'], {}) or {}).get('label') or (loads(row['actor'], {}) or {}).get('kind')}
            for row in db.execute('SELECT * FROM notes WHERE target=? ORDER BY id DESC LIMIT ?', (target, limit))]


def add_note(db, target: str, text: str, outcome: str = 'tip', actor: dict | None = None) -> dict:
    text = re.sub(r'\s+', ' ', str(text or '')).strip()
    if len(text) < 8:
        raise Invalid('A note should be a full sentence about what you learned.')
    if outcome not in OUTCOMES:
        raise Invalid(f'outcome must be one of: {", ".join(OUTCOMES)}.')
    with transaction(db):
        db.execute('INSERT INTO notes (target, text, outcome, actor, at) VALUES (?,?,?,?,?)',
                   (target, text[:1200], outcome, dumps(actor or {}), now()))
        note_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]
    return {'id': note_id, 'target': target, 'text': text[:1200], 'outcome': outcome}


def remove_note(db, note_id: int) -> None:
    with transaction(db):
        db.execute('DELETE FROM notes WHERE id=?', (int(note_id),))


def set_status(db, resource_id: str, *, status: str | None = None, verified: bool | None = None) -> dict:
    key = resource_id.removeprefix('tool:')
    if not db.execute('SELECT 1 FROM resources WHERE id=?', (key,)).fetchone():
        raise Invalid('No such tool or resource.')
    with transaction(db):
        if status:
            if status not in STATUSES:
                raise Invalid('status must be published or hidden.')
            db.execute('UPDATE resources SET status=?, updated_at=? WHERE id=?', (status, now(), key))
        if verified is not None:
            db.execute('UPDATE resources SET verified_at=?, updated_at=? WHERE id=?',
                       (now() if verified else None, now(), key))
    return get(db, key)
