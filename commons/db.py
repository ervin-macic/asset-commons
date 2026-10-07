"""The catalogue database: schema, connection and small helpers.

One SQLite file holds the library: assets and their full-text index,
collections, moderation history, source sync state and agent pulls. WAL mode
lets the UI lane, the agent-tool lane and a sync job read while one writes;
writers use BEGIN IMMEDIATE so they queue instead of failing.
"""
from __future__ import annotations

import contextlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 5

SCHEMA = """
CREATE TABLE IF NOT EXISTS assets (
  id TEXT PRIMARY KEY,                 -- '<source>:<source_id>'
  source TEXT NOT NULL,                -- see commons.sources.SOURCES
  source_id TEXT NOT NULL,
  type TEXT NOT NULL,                  -- see commons.catalog.TYPES
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  tags TEXT NOT NULL DEFAULT '[]',
  categories TEXT NOT NULL DEFAULT '[]',
  style TEXT,
  license TEXT NOT NULL,               -- id in commons.licenses.LICENSES
  authors TEXT NOT NULL DEFAULT '[]',  -- [{name, url}]
  source_url TEXT,
  thumbnail_url TEXT,
  preview_url TEXT,                    -- larger image or audio preview
  formats TEXT NOT NULL DEFAULT '[]',
  resolutions TEXT NOT NULL DEFAULT '[]',
  max_resolution INTEGER,              -- pixels on the longest side
  polycount INTEGER,
  dimensions TEXT,                     -- [x, y, z] metres
  duration REAL,                       -- seconds
  attributes TEXT NOT NULL DEFAULT '{}',
  downloads TEXT,                      -- variant list; NULL until known
  downloads_fetched_at TEXT,
  popularity REAL NOT NULL DEFAULT 0,  -- 0..1 within its source
  published_at TEXT,
  status TEXT NOT NULL DEFAULT 'published',  -- published|pending|rejected|hidden
  origin TEXT NOT NULL DEFAULT 'index',      -- index|submission|upload|federated
  submitted_by TEXT,
  extra_types TEXT NOT NULL DEFAULT '[]',  -- further roles, e.g. an animated model pack
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (source, source_id)
);
CREATE INDEX IF NOT EXISTS assets_status_type ON assets(status, type);
CREATE INDEX IF NOT EXISTS assets_source ON assets(source);

CREATE VIRTUAL TABLE IF NOT EXISTS assets_fts USING fts5(
  title, tags, categories, description, authors, source, contents,
  tokenize = 'porter unicode61 remove_diacritics 2'
);

CREATE TABLE IF NOT EXISTS sources (
  id TEXT PRIMARY KEY,
  last_sync_at TEXT,
  last_status TEXT,
  last_message TEXT,
  asset_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS collections (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  cover_asset_id TEXT,
  tags TEXT NOT NULL DEFAULT '[]',
  curator TEXT,
  status TEXT NOT NULL DEFAULT 'published',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS collection_items (
  collection_id TEXT NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
  asset_id TEXT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
  position INTEGER NOT NULL DEFAULT 0,
  note TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (collection_id, asset_id)
);

CREATE TABLE IF NOT EXISTS moderation_events (
  id INTEGER PRIMARY KEY,
  asset_id TEXT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
  action TEXT NOT NULL,                -- submitted|approved|rejected|hidden|edited
  actor TEXT,
  note TEXT NOT NULL DEFAULT '',
  at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pulls (
  id INTEGER PRIMARY KEY,
  asset_id TEXT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
  variant TEXT,
  dest TEXT,
  actor TEXT,
  bytes INTEGER,
  at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS pulls_asset ON pulls(asset_id);

-- Tools and resources: generators, other asset libraries and utilities that
-- agents can use, curated or added by agents and people.
CREATE TABLE IF NOT EXISTS resources (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  url TEXT NOT NULL,
  kind TEXT NOT NULL,                  -- generator | library | tool
  makes TEXT NOT NULL DEFAULT '[]',    -- what it produces or offers (asset types and more)
  inputs TEXT NOT NULL DEFAULT '[]',
  formats TEXT NOT NULL DEFAULT '[]',
  access TEXT NOT NULL DEFAULT '{}',   -- {api, mcp, web, open_source, self_host}
  pricing TEXT NOT NULL DEFAULT 'unknown',
  pricing_note TEXT NOT NULL DEFAULT '',
  output_terms TEXT NOT NULL DEFAULT '',
  description TEXT NOT NULL DEFAULT '',
  how_to_use TEXT NOT NULL DEFAULT '',
  tags TEXT NOT NULL DEFAULT '[]',
  origin TEXT NOT NULL DEFAULT 'curated',  -- curated | agent | owner
  added_by TEXT,
  verified_at TEXT,
  status TEXT NOT NULL DEFAULT 'published',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS resources_fts USING fts5(
  name, tags, makes, description, how_to_use,
  tokenize = 'porter unicode61 remove_diacritics 2'
);

-- Field notes: what agents and people learned using an asset or tool.
CREATE TABLE IF NOT EXISTS notes (
  id INTEGER PRIMARY KEY,
  target TEXT NOT NULL,                -- an asset id or 'tool:<resource id>'
  text TEXT NOT NULL,
  outcome TEXT NOT NULL DEFAULT 'tip', -- worked | problem | tip
  actor TEXT,
  at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS notes_target ON notes(target);

CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

-- Entry pages still to read for sources listed faster than their pages can be
-- fetched (OpenGameArt asks for ten seconds between requests).
CREATE TABLE IF NOT EXISTS crawl_queue (
  source TEXT NOT NULL,
  source_id TEXT NOT NULL,
  priority INTEGER NOT NULL DEFAULT 0,  -- 1: someone opened it and is waiting
  rank INTEGER,                         -- position among the most favourited; read first
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  queued_at TEXT NOT NULL,
  PRIMARY KEY (source, source_id)
);

CREATE TABLE IF NOT EXISTS remote_cache (  -- live-source responses, kept at most an hour
  key TEXT PRIMARY KEY,
  body TEXT NOT NULL,
  fetched_at REAL NOT NULL
);
"""


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def storage_dir() -> Path:
    """The app's private data directory (set by Möbius for services and jobs)."""
    value = os.environ.get('APP_STORAGE_DIR')
    if not value:
        raise RuntimeError('APP_STORAGE_DIR is not set; run inside Möbius or pass a database path.')
    return Path(value)


def default_path() -> Path:
    return storage_dir() / 'catalog' / 'commons.sqlite3'


def connect(path: str | os.PathLike | None = None) -> sqlite3.Connection:
    path = Path(path) if path else default_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA busy_timeout=30000')
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA synchronous=NORMAL')
    if db.execute('PRAGMA user_version').fetchone()[0] < SCHEMA_VERSION:
        with transaction(db):
            rebuild = _drop_outdated_fts(db)
            # Statement by statement: executescript() would commit mid-way.
            for statement in _statements(SCHEMA):
                db.execute(statement)
            _add_missing_columns(db)
            if rebuild:
                _rebuild_asset_fts(db)
            db.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
    return db


# Columns added after a table first shipped: CREATE TABLE IF NOT EXISTS leaves
# an existing table alone, so older libraries gain them here.
_ADDED_COLUMNS = {'assets': {'extra_types': "TEXT NOT NULL DEFAULT '[]'"}}


def _add_missing_columns(db: sqlite3.Connection) -> None:
    for table, columns in _ADDED_COLUMNS.items():
        present = {row[1] for row in db.execute(f'PRAGMA table_info({table})')}
        for name, declaration in columns.items():
            if name not in present:
                db.execute(f'ALTER TABLE {table} ADD COLUMN {name} {declaration}')


def _drop_outdated_fts(db: sqlite3.Connection) -> bool:
    """Drop an asset index without the `contents` column (it is rebuilt below)."""
    exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='assets_fts'").fetchone()
    if not exists:
        return False
    columns = {row[1] for row in db.execute('PRAGMA table_info(assets_fts)')}
    if 'contents' in columns:
        return False
    db.execute('DROP TABLE assets_fts')
    return True


def _rebuild_asset_fts(db: sqlite3.Connection) -> None:
    db.execute("""
        INSERT INTO assets_fts (rowid, title, tags, categories, description, authors, source, contents)
        SELECT a.rowid, a.title,
               (SELECT group_concat(value, ' ') FROM json_each(a.tags)),
               (SELECT group_concat(value, ' ') FROM json_each(a.categories)),
               a.description,
               (SELECT group_concat(json_extract(value, '$.name'), ' ') FROM json_each(a.authors)),
               a.source,
               (SELECT group_concat(value, ' ') FROM json_each(json_extract(a.attributes, '$.contents')))
        FROM assets a""")


def _statements(script: str):
    buffer = ''
    for line in script.splitlines():
        stripped = line.split('--', 1)[0] if not line.strip().startswith('--') else ''
        buffer += stripped + '\n'
        if sqlite3.complete_statement(buffer):
            if buffer.strip():
                yield buffer.strip()
            buffer = ''


@contextlib.contextmanager
def transaction(db: sqlite3.Connection):
    """BEGIN IMMEDIATE … COMMIT, rolled back on any error."""
    db.execute('BEGIN IMMEDIATE')
    try:
        yield db
    except BaseException:
        db.execute('ROLLBACK')
        raise
    else:
        db.execute('COMMIT')


def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def loads(value, default=None):
    if value is None or value == '':
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default
