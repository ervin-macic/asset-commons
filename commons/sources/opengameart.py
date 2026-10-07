"""OpenGameArt importer (https://opengameart.org): community game art, CC0 entries only.

OpenGameArt has no API, so this reads the public site the way a visitor
would, within its robots.txt (ten seconds between requests):

- The advanced search lists CC0 entries by art type, 144 to a page, newest
  first. That gives each entry's page name, title and preview, so a full
  listing pass (about 120 pages) makes every entry searchable by title. It
  runs monthly to notice removals; a short pass for new entries runs daily.
- Each entry's own page adds the author, tags, description, licences and the
  exact files with their sizes. Pages are read in the background through a
  queue, most-favourited first, one request every ~10 s (about two days for
  the first full pass). An agent that opens or downloads an entry that has not
  been read yet gets it read on the spot.
- Kenney also uploads his packs here; they are indexed from kenney.nl instead.

Concept art and documents are not indexed: they are not assets a project
pulls in.
"""
from __future__ import annotations

import hashlib
import html
import math
import re
import time
import urllib.parse
from collections import Counter
from datetime import datetime, timedelta, timezone

from .. import catalog, net, pace, remotezip
from ..db import dumps, loads, now, transaction
from .kenney import UI_TAGS, UI_WORDS, item_names

SOURCE = 'opengameart'
BASE = 'https://opengameart.org'
HOST = 'opengameart.org'
CRAWL_INTERVAL = 10.5    # robots.txt: Crawl-delay 10
DEMAND_INTERVAL = 10.0   # an agent waiting for one entry
PER_PAGE = 144
CC0_TERM = '4'
# OpenGameArt art type -> (search term id, Asset Commons type)
ART_TYPES = {
    '2D Art': (9, 'sprite'), '3D Art': (10, 'model'), 'Music': (12, 'music'),
    'Sound Effect': (13, 'sound'), 'Texture': (14, 'texture'),
}
SKIP_AUTHORS = {'kenney'}          # indexed from kenney.nl directly
FULL_LISTING_DAYS = 30
NEW_LISTING_HOURS = 20
RANKED_PAGES = 2                   # favourites-ordered pages per type, read first
DETAILS_MAX_AGE_DAYS = 14          # a download re-reads an entry page older than this
MAX_ERRORS_IN_A_ROW = 5
DEFAULT_VARIANT: dict = {}         # chosen per entry: attributes['default_variant']
EXCLUDED = 'excluded'              # moderation action for entries left out on purpose
WITHDRAWN = 'withdrawn'


def _text(fragment: str) -> str:
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', fragment or ''))).strip()


def _html_text(fragment: str) -> str:
    """Readable text from a page fragment, keeping paragraphs and list items."""
    text = re.sub(r'<div class="field-label">.*?</div>', ' ', fragment or '', flags=re.S)
    text = re.sub(r'<(script|style)\b.*?</\1>', ' ', text, flags=re.S | re.I)
    text = re.sub(r'<li[^>]*>', '\n- ', text, flags=re.I)
    text = re.sub(r'<br\s*/?>|</p>|</div>|</h\d>|</ul>|</ol>', '\n', text, flags=re.I)
    text = html.unescape(re.sub(r'<[^>]+>', '', text))
    lines = [re.sub(r'[ \t\xa0]+', ' ', line).strip() for line in text.splitlines()]
    out = '\n'.join(line for line in lines if line)
    return re.sub(r'\n{3,}', '\n\n', out).strip()


def listing_url(type_term: int | None, page: int = 0, *, sort: str = 'created', author: str | None = None) -> str:
    params = [('keys', '')]
    if type_term:
        params.append(('field_art_type_tid[]', str(type_term)))
    params += [('field_art_licenses_tid[]', CC0_TERM), ('sort_by', sort), ('sort_order', 'DESC'),
               ('items_per_page', str(PER_PAGE))]
    if author:
        params.append(('name', author))
    if page:
        params.append(('page', str(page)))
    return f'{BASE}/art-search-advanced?' + urllib.parse.urlencode(params)


def entry_url(slug: str) -> str:
    return f'{BASE}/content/{slug}'


def source_id_for(slug: str) -> str:
    """A library id from an entry's page name (some carry encoded characters)."""
    clean = re.sub(r'%[0-9A-Fa-f]{2}', '', slug)
    clean = re.sub(r'[^A-Za-z0-9._~-]+', '-', clean).strip('-._~')[:140]
    if clean != slug:
        clean = f'{clean or "entry"}-{hashlib.sha1(slug.encode()).hexdigest()[:6]}'
    return clean


_ROW = re.compile(r'<div class="views-row views-row-\d+[^"]*">')


def parse_listing(page: str) -> tuple[list[dict], int]:
    """Entries on one search page, and how many entries the search has in all."""
    start = page.find('view-display-id-search_art_advanced')
    body = page[start:] if start >= 0 else page
    end = body.find('class="pager')
    body = body[:end] if end > 0 else body
    total = re.search(r'Displaying\s+\d+\s*-\s*\d+\s+of\s+(\d+)', page)
    cards = []
    for chunk in _ROW.split(body)[1:]:
        link = re.search(r'class="art-preview-title"><a href="/content/([^"?#/]+)">(.*?)</a>', chunk, re.S)
        if not link:
            continue
        card = {'slug': link.group(1), 'title': _text(link.group(2)) or link.group(1)}
        audio = re.search(r"data-ogg-url='([^']*)'\s+data-mp3-url='([^']*)'", chunk)
        image = re.search(r"<img (?:class='audio-image' )?src='(https://[^']+)'", chunk)
        if audio:
            card['audio'] = {'ogg': audio.group(1) or None, 'mp3': audio.group(2) or None}
        if image:
            card['image'] = image.group(1)
        cards.append(card)
    return cards, int(total.group(1)) if total else len(cards)


_FIELD_END = r'(?=<div class="field field-name-|<ul class="links|$)'


def _field(page: str, name: str) -> str:
    match = re.search(r'<div class="field field-name-' + re.escape(name) + r'[\s"].*?' + _FIELD_END, page, re.S)
    return match.group(0) if match else ''


def _date(text: str) -> str | None:
    try:
        stamp = datetime.strptime(text.strip(), '%A, %B %d, %Y - %H:%M')
    except ValueError:
        return None
    return stamp.strftime('%Y-%m-%dT%H:%M:00Z')


def parse_item(page: str) -> dict:
    """Everything an entry page says about the entry."""
    title = re.search(r'field-name-title.*?<h2>(.*?)</h2>', page, re.S)
    author_block = _field(page, 'author-submitter')
    author = re.search(r'<a href="/users/([^"]+)"[^>]*>(.*?)</a>', author_block, re.S)
    preview_block = _field(page, 'field-art-preview')
    images = re.findall(r'<a href="(https://[^"]+)" class="preview-lightbox"><img src=\'(https://[^\']+)\'',
                        preview_block)
    audio = re.search(r"data-ogg-url='([^']*)'\s+data-mp3-url='([^']*)'", preview_block)
    waveform = re.search(r"class='audio-image' src='(https://[^']+)'", preview_block)
    files = []
    files_block = _field(page, 'field-art-files')
    for match in re.finditer(r'<a href="(https://[^"]+)" type="([^"]*)"[^>]*>(.*?)</a>(.*?)(?=<a href="https://|$)',
                             files_block, re.S):
        url, kind, name, rest = match.groups()
        if urllib.parse.urlsplit(url).hostname != HOST:
            continue
        length = re.search(r'length=(\d+)', kind)
        count = re.search(r'dlcount-number[^>]*>(\d+)<', rest)
        files.append({
            'name': (_text(name) or url.rsplit('/', 1)[-1]).replace('/', '_'), 'url': url,
            'mime': kind.split(';', 1)[0].strip() or None,
            'size': int(length.group(1)) if length else None,
            'downloads': int(count.group(1)) if count else 0,
        })
    favorites = re.search(r'field-item[^>]*>\s*(\d+)\s*<', _field(page, 'favorites'))
    node = re.search(r'node/(\d+)', page)
    return {
        'title': _text(title.group(1)) if title else None,
        'author_user': urllib.parse.unquote(author.group(1)) if author else None,
        'author': _text(author.group(2)) if author else None,
        'published_at': _date(_text(re.sub(r'<div class="field-label">.*?</div>', '',
                                           _field(page, 'post-date'), flags=re.S))),
        'art_types': [_text(a) for a in re.findall(r'<a [^>]*>(.*?)</a>', _field(page, 'field-art-type'), re.S)],
        'tags': [_text(a) for a in re.findall(r'<a [^>]*>(.*?)</a>', _field(page, 'field-art-tags'), re.S)],
        'licenses': [_text(n) for n in re.findall(r"<div class='license-name'>(.*?)</div>",
                                                  _field(page, 'field-art-licenses'), re.S)],
        'favorites': int(favorites.group(1)) if favorites else None,
        'images': [{'full': full, 'medium': medium} for full, medium in images],
        'audio': {'ogg': audio.group(1) or None, 'mp3': audio.group(2) or None} if audio else None,
        'waveform': waveform.group(1) if waveform else None,
        'description': _html_text(_field(page, 'body')),
        'notice': _html_text(_field(page, 'field-copyright-notice')),
        'files': files,
        'node_id': int(node.group(1)) if node else None,
    }


def _medium(url: str | None) -> str | None:
    return url.replace('/styles/thumbnail/public/', '/styles/medium/public/', 1) if url else None


def classify(art_type: str, title: str, tags: list[str]) -> tuple[str, list[str]]:
    kind = ART_TYPES[art_type][1]
    lowered = {t.lower() for t in tags}
    text = ' '.join([title, *tags]).lower()
    extra: list[str] = []
    if kind == 'sprite' and (lowered & UI_TAGS or UI_WORDS.search(title)):
        kind = 'ui'
    if kind == 'model':
        if re.search(r'\banimations?\b', title, re.I) and not re.search(r'\b(character|model|mesh|kit)\b', title, re.I):
            kind = 'animation'
        elif lowered & {'animated', 'animation', 'animations'} or re.search(r'\banimated\b', title, re.I):
            extra.append('animation')
    if kind in ('texture', 'sprite') and re.search(r'\bsky ?box(es)?\b|\bcube ?map\b', text):
        extra.append('hdri')
    return kind, extra


def style_for(kind: str, title: str, tags: list[str]) -> str | None:
    if kind in ('music', 'sound'):
        return None
    text = ' '.join([title, *tags]).lower()
    if re.search(r'pixel|\b(8|16|32)[\s-]?bit\b|\b(8|16|32|64)x\1\b', text):
        return 'pixel'
    if re.search(r'low[\s-]?poly', text):
        return 'low-poly'
    if re.search(r'hand[\s-]?painted', text):
        return 'hand-painted'
    if re.search(r'\b(toon|cel[\s-]?shad\w*)\b', text):
        return 'toon'
    if re.search(r'\b(photo\w*|realistic|scanned|photogrammetry)\b', text):
        return 'realistic'
    if re.search(r'\b(cartoon\w*|stylized|stylised)\b', text):
        return 'stylized'
    return None


def _duration(text: str) -> float | None:
    match = re.search(r'\b(?:length|duration|running time|runtime|time)\s*[:=-]?\s*(\d{1,2}):([0-5]\d)\b', text or '', re.I)
    return float(int(match.group(1)) * 60 + int(match.group(2))) if match else None


def _ext(name: str) -> str:
    return name.rsplit('.', 1)[-1].lower() if '.' in name else ''


def _group(variant_id: str, label: str, fmt: str | None, files: list[dict]) -> dict:
    sizes = [f.get('size') for f in files]
    return {'id': variant_id, 'label': label, 'resolution': None, 'format': fmt, 'group': True,
            'archive': 'zip' if any(_ext(f['name']) == 'zip' for f in files) else None,
            'size': sum(sizes) if all(s is not None for s in sizes) else None,
            'files': [{'path': f['name'], 'url': f['url'], 'size': f.get('size'), 'md5': None} for f in files]}


def variants_for(kind: str, files: list[dict], audio: dict | None) -> list[dict]:
    """Download variants: every file at once, all files of one audio format, each file alone and, for
    audio, OpenGameArt's streaming copies."""
    variants = []
    if len(files) > 1:
        variants.append(_group('all', f'All {len(files)} files', None, files))
    by_format: dict[str, list[dict]] = {}
    for f in files:
        by_format.setdefault(_ext(f['name']), []).append(f)
    if len(by_format) > 1:  # e.g. a track and its loop, each as OGG and WAV: offer "all OGG files"
        for fmt, group in by_format.items():
            if fmt in _AUDIO and len(group) > 1:
                variants.append(_group(f'all-{fmt}', f'All {len(group)} {fmt.upper()} files', fmt, group))
    for f in files:
        ext = _ext(f['name'])
        variants.append({'id': f['name'], 'label': f['name'], 'resolution': None, 'format': ext or None,
                         'archive': 'zip' if ext == 'zip' else None, 'size': f.get('size'),
                         'files': [{'path': f['name'], 'url': f['url'], 'size': f.get('size'), 'md5': None}]})
    if kind in ('music', 'sound') and audio:
        originals = {f['url'] for f in files}
        for fmt in ('ogg', 'mp3'):
            url = audio.get(fmt)
            if not url or url in originals or urllib.parse.urlsplit(url).hostname != HOST:
                continue
            name = re.sub(r'\.(?:mp3|ogg|wav|flac|aiff?)\.(ogg|mp3)$', r'.\1', urllib.parse.unquote(url.rsplit('/', 1)[-1]))
            variants.append({'id': f'preview-{fmt}', 'label': f'{fmt.upper()} preview (OpenGameArt’s streaming copy)',
                             'resolution': None, 'format': fmt, 'archive': None, 'size': None, 'group': True,
                             'files': [{'path': name.replace('/', '_'), 'url': url, 'size': None, 'md5': None}]})
    return variants


SMALL_ORIGINAL = 8 * 1024 * 1024  # a lossless sound-effect original up to this size beats the streaming copy
_AUDIO = {'ogg', 'mp3', 'wav', 'flac', 'aif', 'aiff', 'opus', 'm4a'}


def default_variant(kind: str, variants: list[dict]) -> str | None:
    """What a project most likely wants.

    Audio-only entries take game-ready files: music its OGG (or MP3) files,
    else OpenGameArt's OGG copy rather than a large WAV; sound effects their
    OGG files, then WAV/FLAC (a lone recording only up to 8 MB), then MP3, then
    the OGG copy. Anything else (sprites, models, zips, mixed): every file.
    """
    if not variants:
        return None
    ids = {v['id'] for v in variants}
    singles = [v for v in variants if not v.get('group')]
    if kind in ('music', 'sound') and all(v['format'] in _AUDIO for v in singles):
        order = ('ogg', 'mp3') if kind == 'music' else ('ogg', 'wav', 'flac', 'mp3')
        for fmt in order:
            group = [v for v in singles if v['format'] == fmt]
            if len(group) == 1 and (fmt in ('ogg', 'mp3') or (group[0].get('size') or 0) <= SMALL_ORIGINAL):
                return group[0]['id']
            if len(group) > 1:
                return f'all-{fmt}' if f'all-{fmt}' in ids else 'all'
        if 'preview-ogg' in ids:
            return 'preview-ogg'
    return 'all' if 'all' in ids else variants[0]['id']


def listing_record(card: dict, art_type: str) -> dict:
    """A searchable entry from its listing card alone (title, type, preview)."""
    kind, extra = classify(art_type, card['title'], [])
    audio = card.get('audio') or {}
    thumb = card.get('image')
    return {
        'source': SOURCE, 'source_id': source_id_for(card['slug']), 'type': kind, 'extra_types': extra,
        'title': card['title'], 'description': '', 'tags': [], 'categories': [art_type],
        'style': style_for(kind, card['title'], []), 'license': 'CC0-1.0', 'authors': [],
        'source_url': entry_url(card['slug']), 'thumbnail_url': _medium(thumb),
        'preview_url': audio.get('mp3') or audio.get('ogg') or _medium(thumb),
        'formats': [], 'downloads': None, 'popularity': 0.15,
        'attributes': {'slug': card['slug'], 'art_type': art_type, 'details': 'pending',
                       'thumb_small': thumb, 'audio_preview': audio or None, 'listed_at': now()},
    }


def build(slug: str, detail: dict, art_type_hint: str | None = None, previous: dict | None = None
          ) -> tuple[dict | None, str | None]:
    """A full record from an entry page, or (None, why) when it does not belong in the library."""
    if not any(name.strip().upper() == 'CC0' for name in detail.get('licenses') or []):
        return None, 'It is no longer offered under CC0 on OpenGameArt.'
    if (detail.get('author_user') or '').lower() in SKIP_AUTHORS:
        return None, 'Kenney’s packs are indexed from kenney.nl directly.'
    art_type = next((t for t in detail.get('art_types') or [] if t in ART_TYPES), None)
    if art_type is None:
        if detail.get('art_types'):
            return None, f'{detail["art_types"][0]} entries are not indexed.'
        art_type = art_type_hint if art_type_hint in ART_TYPES else None
        if art_type is None:
            return None, 'The entry page did not say what kind of art it is.'
    previous = previous or {}
    title = detail.get('title') or previous.get('title') or slug
    tags = [t for t in detail.get('tags') or [] if t and not t.startswith('.')]
    kind, extra = classify(art_type, title, tags)
    files = detail.get('files') or []
    audio = detail.get('audio') or (previous.get('attributes') or {}).get('audio_preview')
    variants = variants_for(kind, files, audio)
    images = detail.get('images') or []
    old_attributes = previous.get('attributes') or {}
    thumb_small = old_attributes.get('thumb_small')
    if kind in ('music', 'sound'):
        thumbnail = detail.get('waveform') or _medium(thumb_small)
        preview = (audio or {}).get('mp3') or (audio or {}).get('ogg')
    else:
        thumbnail = images[0]['medium'] if images else _medium(thumb_small)
        preview = images[0]['full'] if images else thumbnail
    total_downloads = sum(f.get('downloads') or 0 for f in files)
    formats = sorted({_ext(f['name']) for f in files if _ext(f['name'])}
                     | ({fmt for fmt in ('ogg', 'mp3') if (audio or {}).get(fmt)} if kind in ('music', 'sound') else set()))
    description = detail.get('description') or ''
    attributes = {
        'slug': slug, 'art_type': art_type, 'details': 'complete', 'page_fetched_at': now(),
        'node_id': detail.get('node_id'), 'licenses_offered': detail.get('licenses') or [],
        'copyright_notice': detail.get('notice') or None, 'favorites': detail.get('favorites'),
        'source_downloads': total_downloads, 'thumb_small': thumb_small or thumbnail,
        'previews': [image['full'] for image in images[:8]], 'audio_preview': audio or None,
        'submitter': detail.get('author_user'), 'default_variant': default_variant(kind, variants),
        'listed_at': old_attributes.get('listed_at'),
    }
    for key in ('files', 'contents', 'contents_from'):  # zip listings read earlier stay while the files do
        if key in old_attributes and old_attributes.get('contents_from') == [f['url'] for f in files]:
            attributes[key] = old_attributes[key]
    if attributes.get('contents_from'):
        formats = sorted(set(formats) | {_ext(n) for n in attributes.get('files') or [] if _ext(n) in _INNER_FORMATS})
    author_url = f'{BASE}/users/{urllib.parse.quote(detail["author_user"])}' if detail.get('author_user') else None
    return {
        'source': SOURCE, 'source_id': source_id_for(slug), 'type': kind, 'extra_types': extra,
        'title': title, 'description': description, 'tags': tags, 'categories': [art_type],
        'style': style_for(kind, title, tags), 'license': 'CC0-1.0',
        'authors': [{'name': detail['author'], 'url': author_url}] if detail.get('author') else [],
        'source_url': entry_url(slug), 'thumbnail_url': thumbnail, 'preview_url': preview,
        'formats': formats, 'duration': _duration(description) if kind in ('music', 'sound') else None,
        'attributes': attributes, 'downloads': variants,
        'popularity': round(min(1.0, math.log10(1 + total_downloads) / 5.0), 3),
        'published_at': detail.get('published_at'),
    }, None


_INNER_FORMATS = {'glb', 'gltf', 'fbx', 'obj', 'blend', 'dae', 'png', 'jpg', 'jpeg', 'gif', 'svg', 'psd', 'ase',
                  'aseprite', 'ogg', 'wav', 'mp3', 'flac', 'ttf', 'otf', 'tmx', 'json'}


# -- On demand (agent tools) ----------------------------------------------------------------------

def needs_details(asset: dict, max_age_days: float | None = None) -> bool:
    attributes = asset.get('attributes') or {}
    if attributes.get('details') != 'complete':
        return True
    if max_age_days is None:
        return False
    try:
        fetched = datetime.fromisoformat(str(attributes.get('page_fetched_at')).replace('Z', '+00:00'))
    except ValueError:
        return True
    return datetime.now(timezone.utc) - fetched > timedelta(days=max_age_days)


def _get(url: str) -> str:
    return net.get_text(url, timeout=30)


def fetch_record(asset: dict, *, get=None, max_wait: float | None = 60, sleep=time.sleep
                 ) -> tuple[dict | None, str | None]:
    """Read one entry's page now (paced) and return its full record, or (None, why)."""
    attributes = asset.get('attributes') or {}
    slug = attributes.get('slug') or asset['source_id']
    pace.wait(HOST, DEMAND_INTERVAL, max_wait=max_wait, sleep=sleep)
    detail = parse_item((get or _get)(entry_url(slug)))
    return build(slug, detail, attributes.get('art_type'), asset)


def read_contents(asset: dict, limit: int = 3) -> dict | None:
    """File lists of the entry's zips (one or two small range requests each), for search and pick."""
    zips = [v for v in asset.get('downloads') or [] if v.get('archive') == 'zip' and len(v.get('files') or []) == 1]
    if not zips or (asset.get('attributes') or {}).get('contents_from') is not None:
        return None
    names: list[str] = []
    for variant in zips[:limit]:
        file = variant['files'][0]
        try:
            members = remotezip.index(file['url'])
        except net.FetchError:
            continue
        inner = [m.name for m in members if not m.name.endswith('/')]
        names += inner if len(zips) == 1 else [f'{file["path"]}/{n}' for n in inner]
    attributes = dict(asset.get('attributes') or {})
    attributes.update({'files': names[:3000], 'contents': item_names(names),
                       'contents_from': [f['url'] for v in asset.get('downloads') or [] if v['id'] != 'all'
                                         and not v['id'].startswith('preview-') for f in v['files']]})
    formats = sorted(set(asset.get('formats') or []) | {_ext(n) for n in names if _ext(n) in _INNER_FORMATS})
    return {**asset, 'attributes': attributes, 'formats': formats}


# -- Background crawl (the sync job) ----------------------------------------------------------------

def _state(conn) -> dict:
    row = conn.execute("SELECT value FROM meta WHERE key='opengameart_state'").fetchone()
    return loads(row[0], {}) if row else {}


def _save_state(conn, state: dict) -> None:
    with transaction(conn):
        conn.execute("INSERT INTO meta (key, value) VALUES ('opengameart_state', ?) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (dumps(state),))


def _older(stamp: str | None, **delta) -> bool:
    if not stamp:
        return True
    try:
        then = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
    except ValueError:
        return True
    return datetime.now(timezone.utc) - then > timedelta(**delta)


def queue_counts(conn) -> dict:
    waiting = conn.execute('SELECT COUNT(*) FROM crawl_queue WHERE source=?', (SOURCE,)).fetchone()[0]
    priority = conn.execute('SELECT COUNT(*) FROM crawl_queue WHERE source=? AND priority > 0',
                            (SOURCE,)).fetchone()[0]
    return {'waiting': waiting, 'priority': priority}


def request_details(conn, asset_id: str) -> None:
    """Move one entry to the front of the background queue (someone is looking at it)."""
    source_id = asset_id.split(':', 1)[1]
    with transaction(conn):
        conn.execute('INSERT INTO crawl_queue (source, source_id, priority, queued_at) VALUES (?,?,1,?) '
                     'ON CONFLICT(source, source_id) DO UPDATE SET priority=1', (SOURCE, source_id, now()))


def _event(conn, asset_id: str, action: str, note: str) -> None:
    conn.execute('INSERT INTO moderation_events (asset_id, action, actor, note, at) VALUES (?,?,?,?,?)',
                 (asset_id, action, dumps({'kind': 'sync', 'source': SOURCE}), note[:500], now()))


def _last_actions(conn) -> dict[str, str]:
    rows = conn.execute(
        "SELECT a.source_id, (SELECT action FROM moderation_events m WHERE m.asset_id=a.id ORDER BY m.id DESC "
        "LIMIT 1) FROM assets a WHERE a.source=? AND a.status='hidden'", (SOURCE,)).fetchall()
    return {row[0]: row[1] for row in rows}


def apply_detail(conn, asset: dict, record: dict | None, reason: str | None) -> str:
    """Store what an entry page said: the full record, or leave the entry out with the reason."""
    with transaction(conn):
        conn.execute('DELETE FROM crawl_queue WHERE source=? AND source_id=?', (SOURCE, asset['source_id']))
        if record is None:
            if asset.get('status') == 'published':
                conn.execute("UPDATE assets SET status='hidden', updated_at=? WHERE id=?", (now(), asset['id']))
                _event(conn, asset['id'], EXCLUDED, reason or 'Left out.')
            return 'excluded'
        catalog.upsert(conn, record)
        return 'read'


def withdraw(conn, asset: dict, note: str) -> None:
    with transaction(conn):
        conn.execute('DELETE FROM crawl_queue WHERE source=? AND source_id=?', (SOURCE, asset['source_id']))
        if asset.get('status') == 'published':
            conn.execute("UPDATE assets SET status='hidden', updated_at=? WHERE id=?", (now(), asset['id']))
            _event(conn, asset['id'], WITHDRAWN, note)


def _store_cards(conn, cards: list[dict], art_type: str, skip: set[str], seen: set[str], counts: Counter) -> int:
    """Add entries the library does not have yet; returns how many were new."""
    new = 0
    with transaction(conn):
        for card in cards:
            if card['slug'] in skip:
                counts['skipped (Kenney)'] += 1
                continue
            source_id = source_id_for(card['slug'])
            seen.add(source_id)
            if conn.execute('SELECT 1 FROM assets WHERE id=?', (f'{SOURCE}:{source_id}',)).fetchone():
                continue
            try:
                catalog.upsert(conn, listing_record(card, art_type))
            except catalog.Invalid:
                counts['invalid'] += 1
                continue
            conn.execute('INSERT OR IGNORE INTO crawl_queue (source, source_id, priority, queued_at) '
                         'VALUES (?,?,0,?)', (SOURCE, source_id, now()))
            counts['listed'] += 1
            new += 1
    return new


class _Crawler:
    """One sync run: listing passes, then entry pages from the queue, paced throughout."""

    def __init__(self, conn, log, get=None, sleep=time.sleep, max_items: int | None = None):
        self.conn, self.log, self.sleep, self.max_items = conn, log, sleep, max_items
        self._get = get or _get
        self.counts: Counter = Counter()
        self.read = 0
        self.errors_in_a_row = 0

    def fetch(self, url: str) -> str:
        pace.wait(HOST, CRAWL_INTERVAL, sleep=self.sleep)
        return self._get(url)

    def progress(self, phase: str) -> None:
        left = queue_counts(self.conn)['waiting']
        with transaction(self.conn):
            self.conn.execute("INSERT INTO meta (key, value) VALUES ('opengameart_progress', ?) "
                              "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                              (dumps({'at': now(), 'phase': phase, 'read': self.read, 'waiting': left}),))

    def kenney_slugs(self) -> set[str]:
        slugs: set[str] = set()
        page = 0
        while page < 5:
            cards, total = parse_listing(self.fetch(listing_url(None, page, author='Kenney')))
            slugs.update(card['slug'] for card in cards)
            page += 1
            if not cards or page * PER_PAGE >= total:
                break
        return slugs

    def full_listing(self, state: dict) -> None:
        skip = self.kenney_slugs()
        with transaction(self.conn):
            self.conn.execute("INSERT INTO meta (key, value) VALUES ('opengameart_kenney', ?) "
                              "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (dumps(sorted(skip)),))
        seen: set[str] = set()
        complete = True
        for art_type, (term, _) in ART_TYPES.items():
            page = 0
            while True:
                try:
                    cards, total = parse_listing(self.fetch(listing_url(term, page)))
                except net.FetchError as exc:
                    self.log(f'  OpenGameArt {art_type} page {page}: {exc}')
                    complete = False
                    break
                _store_cards(self.conn, cards, art_type, skip, seen, self.counts)
                self.progress('listing')
                self.serve_priority()
                page += 1
                if not cards or page * PER_PAGE >= total or page > 400:
                    break
        self.log(f'OpenGameArt: {len(seen):,} CC0 entries listed.')
        with transaction(self.conn):
            for slug in skip:  # anything stored before Kenney's uploads were known
                row = catalog.get(self.conn, f'{SOURCE}:{source_id_for(slug)}')
                if row and row['status'] == 'published':
                    self.conn.execute("UPDATE assets SET status='hidden' WHERE id=?", (row['id'],))
                    _event(self.conn, row['id'], EXCLUDED, 'Kenney’s packs are indexed from kenney.nl directly.')
                    self.conn.execute('DELETE FROM crawl_queue WHERE source=? AND source_id=?',
                                      (SOURCE, row['source_id']))
        if complete:
            self.reconcile(seen)
            state['full_at'] = state['new_at'] = now()
        self.rank()

    def reconcile(self, seen: set[str]) -> None:
        """Withdraw entries no longer listed as CC0; bring back withdrawn ones listed again."""
        published = [row[0] for row in self.conn.execute(
            "SELECT source_id FROM assets WHERE source=? AND origin='index' AND status='published'", (SOURCE,))]
        last = _last_actions(self.conn)
        with transaction(self.conn):
            for source_id, action in last.items():
                if action == WITHDRAWN and source_id in seen:
                    self.conn.execute("UPDATE assets SET status='published' WHERE id=?", (f'{SOURCE}:{source_id}',))
                    _event(self.conn, f'{SOURCE}:{source_id}', 'restored', 'Listed as CC0 again.')
                    self.conn.execute('INSERT OR IGNORE INTO crawl_queue (source, source_id, priority, queued_at) '
                                      'VALUES (?,?,0,?)', (SOURCE, source_id, now()))
                    self.counts['restored'] += 1
            if published and len(seen) >= 0.8 * len(published):
                for source_id in published:
                    if source_id not in seen:
                        self.conn.execute("UPDATE assets SET status='hidden' WHERE id=?", (f'{SOURCE}:{source_id}',))
                        _event(self.conn, f'{SOURCE}:{source_id}', WITHDRAWN, 'No longer listed as CC0.')
                        self.conn.execute('DELETE FROM crawl_queue WHERE source=? AND source_id=?', (SOURCE, source_id))
                        self.counts['withdrawn'] += 1

    def new_listing(self, state: dict) -> None:
        row = self.conn.execute("SELECT value FROM meta WHERE key='opengameart_kenney'").fetchone()
        skip = set(loads(row[0], [])) if row else set()
        for art_type, (term, _) in ART_TYPES.items():
            for page in range(5):
                try:
                    cards, total = parse_listing(self.fetch(listing_url(term, page)))
                except net.FetchError as exc:
                    self.log(f'  OpenGameArt {art_type}: {exc}')
                    return
                fresh = _store_cards(self.conn, cards, art_type, skip, set(), self.counts)
                self.serve_priority()
                if not fresh or (page + 1) * PER_PAGE >= total:
                    break
        state['new_at'] = now()

    def rank(self) -> None:
        """Queue the most-favourited entries of each type first (interleaved by position)."""
        for page in range(RANKED_PAGES):
            for art_type, (term, _) in ART_TYPES.items():
                try:
                    cards, _ = parse_listing(self.fetch(listing_url(term, page, sort='count')))
                except net.FetchError:
                    continue
                with transaction(self.conn):
                    for offset, card in enumerate(cards):
                        position = page * PER_PAGE + offset
                        self.conn.execute('UPDATE crawl_queue SET rank=? WHERE source=? AND source_id=? '
                                          'AND (rank IS NULL OR rank > ?)',
                                          (position, SOURCE, source_id_for(card['slug']), position))

    def next_item(self, only_priority: bool = False):
        sql = ('SELECT source_id, priority, attempts FROM crawl_queue WHERE source=?'
               + (' AND priority > 0' if only_priority else '')
               + ' ORDER BY priority DESC, rank IS NULL, rank, queued_at LIMIT 1')
        return self.conn.execute(sql, (SOURCE,)).fetchone()

    def read_one(self, row) -> bool:
        """Read one queued entry page; False when the run should stop (the site keeps failing)."""
        asset = catalog.get(self.conn, f'{SOURCE}:{row["source_id"]}')
        if asset is None or not needs_details(asset):  # gone, or read on demand meanwhile
            with transaction(self.conn):
                self.conn.execute('DELETE FROM crawl_queue WHERE source=? AND source_id=?', (SOURCE, row['source_id']))
            return True
        attributes = asset.get('attributes') or {}
        slug = attributes.get('slug') or asset['source_id']
        try:
            detail = parse_item(self.fetch(entry_url(slug)))
        except net.FetchError as exc:
            if exc.status in (404, 410):
                withdraw(self.conn, asset, 'Removed from OpenGameArt.')
                self.counts['removed'] += 1
                return True
            self.errors_in_a_row += 1
            with transaction(self.conn):
                if row['attempts'] + 1 >= 3:
                    self.conn.execute('DELETE FROM crawl_queue WHERE source=? AND source_id=?', (SOURCE, row['source_id']))
                else:
                    self.conn.execute('UPDATE crawl_queue SET attempts=attempts+1, last_error=?, rank=NULL, '
                                      'priority=0 WHERE source=? AND source_id=?',
                                      (str(exc)[:300], SOURCE, row['source_id']))
            self.counts['errors'] += 1
            self.log(f'  OpenGameArt {slug}: {exc}')
            return self.errors_in_a_row < MAX_ERRORS_IN_A_ROW
        self.errors_in_a_row = 0
        record, reason = build(slug, detail, attributes.get('art_type'), asset)
        try:
            outcome = apply_detail(self.conn, asset, record, reason)
        except catalog.Invalid as exc:
            outcome = 'invalid'
            with transaction(self.conn):
                self.conn.execute('DELETE FROM crawl_queue WHERE source=? AND source_id=?', (SOURCE, row['source_id']))
            self.log(f'  OpenGameArt {slug}: {exc}')
        self.counts[outcome] += 1
        self.read += 1
        return True

    def serve_priority(self) -> None:
        row = self.next_item(only_priority=True)
        if row is not None:
            self.read_one(row)

    def read_queue(self) -> None:
        while self.max_items is None or self.read < self.max_items:
            row = self.next_item()
            if row is None or not self.read_one(row):
                break
            if self.read % 25 == 0:
                self.progress('reading')
                self.status('running')
        self.progress('idle')

    def status(self, state: str) -> None:
        total = self.conn.execute("SELECT COUNT(*) FROM assets WHERE source=? AND status='published'",
                                  (SOURCE,)).fetchone()[0]
        parts = [', '.join(f'{k} {v}' for k, v in sorted(self.counts.items()))]
        waiting = queue_counts(self.conn)['waiting']
        if waiting:
            hours = waiting * CRAWL_INTERVAL / 3600
            parts.append(f'{waiting:,} entry pages still to read' + (f' (about {hours:.0f} h)' if hours >= 1 else ''))
        message = '; '.join(part for part in parts if part)
        with transaction(self.conn):
            self.conn.execute('INSERT INTO sources (id, last_sync_at, last_status, last_message, asset_count) '
                              'VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET last_sync_at=excluded.last_sync_at, '
                              'last_status=excluded.last_status, last_message=excluded.last_message, '
                              'asset_count=excluded.asset_count', (SOURCE, now(), state, message[:500], total))


def run(conn, log=print, *, refresh: bool = False, get=None, sleep=time.sleep, max_items: int | None = None) -> dict:
    """One sync run. A newer ready-made catalogue first, listing passes when due, then entry pages
    until the queue is empty."""
    from .. import seed  # imported here: the seed module builds on this one
    try:
        seed.import_newest(conn, log)
    except Exception as exc:  # noqa: BLE001 - a bad seed must never stop the crawl
        log(f'OpenGameArt seed import failed: {exc}')
    crawler = _Crawler(conn, log, get=get, sleep=sleep, max_items=max_items)
    state = _state(conn)
    try:
        if refresh or _older(state.get('full_at'), days=FULL_LISTING_DAYS):
            crawler.full_listing(state)
        elif _older(state.get('new_at'), hours=NEW_LISTING_HOURS):
            crawler.new_listing(state)
        _save_state(conn, state)
        crawler.read_queue()
    except Exception:
        crawler.status('error')
        raise
    crawler.status('ok')
    published = conn.execute("SELECT COUNT(*) FROM assets WHERE source=? AND status='published'",
                             (SOURCE,)).fetchone()[0]
    log(f'OpenGameArt: {", ".join(f"{k} {v}" for k, v in sorted(crawler.counts.items())) or "nothing new"}; '
        f'{published:,} published.')
    return {'source': SOURCE, 'counts': dict(crawler.counts), 'published': published}
