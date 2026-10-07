"""Freesound live source (https://freesound.org): CC0 sounds searched on demand.

Freesound's API terms allow only limited intermediate copies of its content
and forbid building a parallel database, so Asset Commons never bulk-indexes
it. Searches and sound details are fetched live with the owner's API key, which
the app's own service reads from Möbius's encrypted secret store (the browser
frame can save the key but never read it back). Responses are cached for an
hour to stay inside Freesound's limits (60 requests a minute, 2,000 a day), and
a sound is stored locally only once someone downloads it, as provenance for
credits.

Downloads are Freesound's high-quality previews (OGG/MP3), which need no
authentication. Original files require a per-user OAuth2 login on Freesound,
so they stay a link to the sound's page.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from .. import USER_AGENT, net
from ..db import now

API = 'https://freesound.org/apiv2'
SECRET_NAME = 'freesound-key'
CACHE_SECONDS = 3600
CC0_FILTER = 'license:"Creative Commons 0"'
FIELDS = ('id,name,tags,description,username,license,duration,samplerate,channels,type,filesize,'
          'num_downloads,avg_rating,created,previews,images,url,pack')
SORTS = {'relevance': 'score', 'popular': 'downloads_desc', 'newest': 'created_desc', 'name': 'score'}
DEFAULT_VARIANT = {'sound': ['hq-ogg', 'hq-mp3']}
_AUDIO_EXT = re.compile(r'\.(wav|wave|mp3|ogg|oga|flac|aiff?|m4a|caf)$', re.I)


class NotConnected(Exception):
    """No Freesound key has been saved in Asset Commons."""


class Rejected(Exception):
    """Freesound refused the saved key."""


class Throttled(Exception):
    """Freesound's rate limit was reached."""


# --- The owner's key ------------------------------------------------------------------------

def read_key() -> str:
    """The saved API key, read by the app's own service from Möbius's encrypted store."""
    base, app_id, token = os.environ.get('API_BASE_URL'), os.environ.get('APP_ID'), os.environ.get('APP_TOKEN')
    if not (base and app_id and token):
        raise NotConnected('Freesound is only available inside the installed app.')
    request = urllib.request.Request(f'{base.rstrip("/")}/api/apps/{app_id}/secrets/{SECRET_NAME}',
                                     headers={'Authorization': f'Bearer {token}'})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            key = response.read(4096).decode('utf-8').strip()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise NotConnected('Connect Freesound in Asset Commons (Sources) to search CC0 sounds.') from exc
        raise NotConnected(f'Möbius could not provide the Freesound key ({exc.code}).') from exc
    except (urllib.error.URLError, OSError) as exc:
        raise NotConnected('Möbius could not provide the Freesound key right now.') from exc
    if not key:
        raise NotConnected('Connect Freesound in Asset Commons (Sources) to search CC0 sounds.')
    return key


# --- Requests, with a short cache ---------------------------------------------------------

def _cache_key(path: str, params: dict) -> str:
    return hashlib.sha256((path + '?' + urllib.parse.urlencode(sorted(params.items()))).encode()).hexdigest()


def _cached(db, key: str):
    if db is None:
        return None
    row = db.execute('SELECT body, fetched_at FROM remote_cache WHERE key=?', (key,)).fetchone()
    if row and time.time() - row['fetched_at'] < CACHE_SECONDS:
        return json.loads(row['body'])
    return None


def forget(db) -> None:
    """Drop every cached Freesound response (after disconnecting the key)."""
    db.execute('DELETE FROM remote_cache')


def _store(db, key: str, body) -> None:
    if db is None:
        return
    stamp = time.time()
    db.execute('BEGIN IMMEDIATE')
    try:
        db.execute('DELETE FROM remote_cache WHERE fetched_at < ?', (stamp - CACHE_SECONDS,))
        db.execute('INSERT OR REPLACE INTO remote_cache (key, body, fetched_at) VALUES (?,?,?)',
                   (key, json.dumps(body, separators=(',', ':')), stamp))
        db.execute('COMMIT')
    except BaseException:
        db.execute('ROLLBACK')
        raise


def api_get(db, path: str, params: dict, *, key: str | None = None, fetch=None, fresh: bool = False):
    """GET one Freesound API resource (cached for an hour unless `fresh`)."""
    cache = _cache_key(path, params)
    hit = None if fresh else _cached(db, cache)
    if hit is not None:
        return hit
    key = key or read_key()
    url = f'{API}/{path.lstrip("/")}?{urllib.parse.urlencode(params)}'
    try:
        body = (fetch or _fetch)(url, key)
    except net.FetchError as exc:
        status = getattr(exc, 'status', None)
        if status == 401:
            raise Rejected('Freesound rejected the saved API key. Reconnect it in Asset Commons (Sources).') from exc
        if status == 429:
            raise Throttled('Freesound’s rate limit was reached (60 a minute, 2,000 a day); try again shortly.') from exc
        if status == 404:
            body = None
        else:
            raise
    if body is not None:
        _store(db, cache, body)
    return body


def _fetch(url: str, key: str):
    return net.get_json(url, timeout=12, max_bytes=8 * 1024 * 1024,
                        headers={'Authorization': f'Token {key}', 'Accept': 'application/json'})


# --- Mapping Freesound sounds onto Asset Commons assets -----------------------------------

def _slug(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')[:60] or 'sound'


def title_of(name: str) -> str:
    return _AUDIO_EXT.sub('', (name or '').strip()) or 'Untitled sound'


def is_cc0(license_value) -> bool:
    text = str(license_value or '').lower()
    return 'publicdomain/zero' in text or text.strip() in ('creative commons 0', 'cc0')


def to_asset(sound: dict) -> dict | None:
    """A Freesound sound as an Asset Commons asset record (not stored)."""
    if not isinstance(sound, dict) or not isinstance(sound.get('id'), int) or not is_cc0(sound.get('license')):
        return None
    previews = sound.get('previews') or {}
    images = sound.get('images') or {}
    title = title_of(sound.get('name'))
    base = f'{sound["id"]}-{_slug(title)}'
    variants = []
    for key, variant_id, fmt, label in (('preview-hq-ogg', 'hq-ogg', 'ogg', 'High-quality OGG (preview)'),
                                         ('preview-hq-mp3', 'hq-mp3', 'mp3', 'High-quality MP3 (preview)'),
                                         ('preview-lq-mp3', 'lq-mp3', 'mp3', 'Small MP3 (preview)')):
        url = previews.get(key)
        if isinstance(url, str) and url.startswith('https://'):
            variants.append({'id': variant_id, 'label': label, 'resolution': None, 'format': fmt, 'size': None,
                             'files': [{'path': f'{base}.{fmt}', 'url': url, 'size': None, 'md5': None}]})
    original = {k: sound.get(k) for k in ('type', 'samplerate', 'channels', 'filesize') if sound.get(k) is not None}
    downloads = sound.get('num_downloads') or 0
    rating = sound.get('avg_rating') or 0
    created = sound.get('created')
    return {
        'id': f'freesound:{sound["id"]}', 'source': 'freesound', 'source_id': str(sound['id']), 'type': 'sound',
        'title': title[:160], 'description': (sound.get('description') or '').strip()[:2000],
        'tags': [t for t in sound.get('tags') or [] if isinstance(t, str)][:40], 'categories': [],
        'style': None, 'license': 'CC0-1.0',
        'authors': [{'name': sound.get('username') or 'Freesound user',
                     'url': f'https://freesound.org/people/{urllib.parse.quote(sound.get("username") or "")}/'}],
        'source_url': sound.get('url') or f'https://freesound.org/s/{sound["id"]}/',
        'thumbnail_url': images.get('waveform_m') or images.get('waveform_l'),
        'preview_url': previews.get('preview-hq-mp3'),
        'formats': ['ogg', 'mp3'], 'resolutions': [], 'max_resolution': None, 'polycount': None,
        'dimensions': None, 'duration': sound.get('duration'),
        'attributes': {'original': original, 'preview_lq': previews.get('preview-lq-mp3'),
                       'folder': base, 'rating': round(rating, 2) if rating else None,
                       'freesound_downloads': downloads},
        'downloads': variants, 'downloads_fetched_at': now(),
        'popularity': min(1.0, (downloads ** 0.25) / 30.0),
        'published_at': (created[:19] + 'Z') if isinstance(created, str) and len(created) >= 19 else None,
        'status': 'published', 'origin': 'live',
    }


def _search(db, params: dict, **options) -> dict:
    """/search/ is Freesound's current endpoint; fall back to the older /search/text/."""
    body = api_get(db, 'search/', params, **options)
    if body is None:
        body = api_get(db, 'search/text/', params, **options)
    return body or {}


def search(db, terms: list[str], *, sort: str = 'relevance', limit: int = 24, offset: int = 0,
           max_duration=None, tags=None, key: str | None = None, fetch=None) -> dict:
    """Live CC0 search. Returns {'total', 'assets', 'next_offset'}."""
    limit = max(1, min(int(limit or 24), 150))
    page = int(offset or 0) // limit + 1
    filters = [CC0_FILTER]
    if max_duration:
        filters.append(f'duration:[0 TO {float(max_duration):g}]')
    for tag in tags or []:
        if re.fullmatch(r'[\w-]{1,40}', tag):
            filters.append(f'tag:{tag}')
    query = ' '.join(terms or [])
    params = {'query': query, 'filter': ' '.join(filters), 'fields': FIELDS, 'page_size': limit, 'page': page,
              'sort': SORTS.get(sort, 'score') if query else ('created_desc' if sort == 'newest' else 'downloads_desc')}
    body = _search(db, params, key=key, fetch=fetch)
    assets = [a for a in (to_asset(s) for s in body.get('results') or []) if a]
    total = int(body.get('count') or 0)
    start = (page - 1) * limit
    return {'total': total, 'assets': assets, 'next_offset': start + limit if start + limit < total else None}


def count(db, terms: list[str], *, max_duration=None, key: str | None = None, fetch=None,
          fresh: bool = False) -> int:
    filters = [CC0_FILTER] + ([f'duration:[0 TO {float(max_duration):g}]'] if max_duration else [])
    body = _search(db, {'query': ' '.join(terms or []), 'filter': ' '.join(filters), 'fields': 'id',
                        'page_size': 1, 'page': 1}, key=key, fetch=fetch, fresh=fresh)
    return int(body.get('count') or 0)


def sound(db, source_id: str, *, key: str | None = None, fetch=None) -> dict | None:
    if not re.fullmatch(r'\d{1,12}', str(source_id)):
        return None
    body = api_get(db, f'sounds/{source_id}/', {'fields': FIELDS}, key=key, fetch=fetch)
    return to_asset(body) if body else None
