#!/usr/bin/env python3
"""Refresh the Asset Commons catalogue from its indexed sources.

    python3 sync.py                     # every indexed source
    python3 sync.py polyhaven           # one source
    python3 sync.py --db /tmp/test.sqlite3 ambientcg

Only catalogue metadata and download listings are fetched (a few megabytes);
asset files are downloaded later, one at a time, when someone asks for them.
Assets a source stops listing are withdrawn (hidden) and come back if the
source lists them again; assets the owner hid stay hidden.

As the scheduled job (Möbius passes the app id), a source is synced when it is
due (not synced successfully for DUE_DAYS), so the app can start the job again
at any time without re-reading everything. OpenGameArt runs last: it lists new
entries, then reads entry pages one every ~10 s until its queue is empty, which
takes about two days the first time. The job may run that long; Möbius runs
one copy at a time and a stopped run resumes where it left off.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import traceback
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from commons import catalog, db as database  # noqa: E402
from commons.db import dumps, now, transaction  # noqa: E402
from commons.sources import SOURCES, importer  # noqa: E402

WITHDRAWN = 'withdrawn'
DUE_DAYS = 6


def due(conn, source: str) -> bool:
    row = conn.execute('SELECT last_sync_at, last_status FROM sources WHERE id=?', (source,)).fetchone()
    if row is None or row['last_status'] != 'ok' or not row['last_sync_at']:
        return True
    try:
        last = datetime.fromisoformat(row['last_sync_at'].replace('Z', '+00:00'))
    except ValueError:
        return True
    return datetime.now(timezone.utc) - last > timedelta(days=DUE_DAYS)


def sync_source(conn, source: str, log=print, refresh: bool = False) -> dict:
    module = importer(source)
    if module is None:
        raise SystemExit(f'{source} has no importer yet.')
    if hasattr(module, 'run'):  # listed quickly, read through a queue (OpenGameArt)
        return module.run(conn, log, refresh=refresh)
    started = now()
    known = {} if refresh else {row['source_id']: catalog.row_dict(row)
                                for row in conn.execute('SELECT * FROM assets WHERE source=?', (source,))}
    vocabulary = set()
    for (tags,) in conn.execute("SELECT lower(tags) FROM assets WHERE origin='index'"):
        vocabulary.update(w for w in re.findall(r'[a-z]+', tags) if len(w) >= 3)
    try:
        records = list(module.fetch_records(log, known=known, vocabulary=vocabulary))
    except Exception as exc:  # network or feed-shape failure: record it, keep the old catalogue
        with transaction(conn):
            conn.execute('INSERT INTO sources (id, last_sync_at, last_status, last_message) VALUES (?,?,?,?) '
                         'ON CONFLICT(id) DO UPDATE SET last_sync_at=excluded.last_sync_at, '
                         'last_status=excluded.last_status, last_message=excluded.last_message',
                         (source, started, 'error', str(exc)[:500]))
        raise
    counts: Counter = Counter()
    seen: set[str] = set()
    previous = conn.execute("SELECT COUNT(*) FROM assets WHERE source=? AND origin='index'", (source,)).fetchone()[0]
    with transaction(conn):
        for record in records:
            try:
                counts[catalog.upsert(conn, record)] += 1
                seen.add(catalog.asset_id(record['source'], record['source_id']))
            except catalog.Invalid as exc:
                counts['skipped'] += 1
                log(f'  skipped {record.get("source_id")}: {exc}')
        # Bring back assets the source lists again after a withdrawal.
        for (asset_id,) in conn.execute(
                "SELECT a.id FROM assets a WHERE a.source=? AND a.status='hidden' AND "
                "(SELECT action FROM moderation_events m WHERE m.asset_id=a.id ORDER BY m.id DESC LIMIT 1)=?",
                (source, WITHDRAWN)).fetchall():
            if asset_id in seen:
                conn.execute("UPDATE assets SET status='published' WHERE id=?", (asset_id,))
                conn.execute('INSERT INTO moderation_events (asset_id, action, actor, note, at) VALUES (?,?,?,?,?)',
                             (asset_id, 'restored', dumps({'kind': 'sync'}), 'Listed by the source again.', now()))
                counts['restored'] += 1
        # Withdraw what the source no longer lists, unless the feed looks truncated.
        if seen and len(seen) >= 0.8 * previous:
            for (asset_id,) in conn.execute(
                    "SELECT id FROM assets WHERE source=? AND origin='index' AND status='published'",
                    (source,)).fetchall():
                if asset_id not in seen:
                    conn.execute("UPDATE assets SET status='hidden' WHERE id=?", (asset_id,))
                    conn.execute('INSERT INTO moderation_events (asset_id, action, actor, note, at) '
                                 'VALUES (?,?,?,?,?)', (asset_id, WITHDRAWN, dumps({'kind': 'sync'}),
                                                        'No longer listed by the source.', now()))
                    counts['withdrawn'] += 1
        total = conn.execute("SELECT COUNT(*) FROM assets WHERE source=? AND status='published'",
                             (source,)).fetchone()[0]
        message = ', '.join(f'{k} {v}' for k, v in sorted(counts.items()))
        conn.execute('INSERT INTO sources (id, last_sync_at, last_status, last_message, asset_count) '
                     'VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET last_sync_at=excluded.last_sync_at, '
                     'last_status=excluded.last_status, last_message=excluded.last_message, '
                     'asset_count=excluded.asset_count', (source, started, 'ok', message, total))
    log(f'{SOURCES[source]["name"]}: {message}; {total} published.')
    return {'source': source, 'counts': dict(counts), 'published': total}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('sources', nargs='*', help='source ids (default: every indexed source)')
    parser.add_argument('--db', help='database path (default: the app storage catalogue)')
    parser.add_argument('--refresh', action='store_true', help='re-read every page instead of reusing recent ones')
    parser.add_argument('--all', action='store_true', help='sync every source now, even ones synced recently')
    args = parser.parse_args(argv)
    # As the scheduled job, Möbius passes the numeric app id first; it is not a source.
    named = [source for source in args.sources if not source.isdigit()]
    app_id = next((source for source in args.sources if source.isdigit()), None)
    _storage_for_job(app_id)
    log = _job_log()
    try:
        conn = database.connect(args.db)
        if not named or 'opengameart' in named:
            try:  # the ready-made catalogue first: a new install has 17,000 entries within seconds
                from commons import seed
                seed.import_newest(conn, log)
            except Exception as exc:  # noqa: BLE001 - never block the sync on a bad seed
                log(f'OpenGameArt seed import failed: {exc}')
        if named:
            chosen = named
        else:
            indexed = [key for key, value in SOURCES.items() if value['status'] == 'indexed']
            queued = [key for key in indexed if hasattr(importer(key), 'run')]  # decide for themselves, run last
            chosen = [key for key in indexed if key not in queued and (args.all or due(conn, key))] + queued
        log(f'sync started: {", ".join(chosen) or "nothing due"}')
    except Exception:
        log('sync could not start:\n' + traceback.format_exc())
        raise
    failures = 0
    for source in chosen:
        try:
            sync_source(conn, source, log=log, refresh=args.refresh)
        except SystemExit:
            raise
        except Exception as exc:
            failures += 1
            log(f'{source}: sync failed: {exc}\n{traceback.format_exc()}')
    log(f'sync finished ({failures} failed)')
    return 1 if failures else 0


def _storage_for_job(app_id: str | None) -> None:
    """Scheduled jobs get DATA_DIR and the app id, not APP_STORAGE_DIR (which the service gets)."""
    if not os.environ.get('APP_STORAGE_DIR') and app_id and os.environ.get('DATA_DIR'):
        os.environ['APP_STORAGE_DIR'] = str(Path(os.environ['DATA_DIR']) / 'apps' / app_id)


def _job_log():
    """print, and when run as the scheduled job also append to job-state/sync.log (its output is not kept)."""
    folder = os.environ.get('APP_JOB_STATE_DIR')
    if not folder:
        return print
    path = Path(folder) / 'sync.log'
    try:
        if path.stat().st_size > 1_000_000:
            path.replace(path.with_suffix('.log.1'))
    except OSError:
        pass

    def log(message: str) -> None:
        print(message)
        try:
            with open(path, 'a', encoding='utf-8') as handle:
                handle.write(f'{now()} {message}\n')
        except OSError:
            pass
    return log


if __name__ == '__main__':
    raise SystemExit(main())
