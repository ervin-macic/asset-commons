"""Kenney importer (https://kenney.nl): CC0 game asset packs, one entry per pack.

Kenney has no API, so the importer reads the public website the way a
visitor would: the paged asset listing, then each pack's page for its tags,
category, series, features, file count, licence, version and download link.
Requests are paced and a pack page is revisited at most every REVISIT_DAYS;
packs seen recently are carried forward from the library instead. Each pack
downloads as Kenney's own zip (3D packs hold GLB, FBX and OBJ versions).
"""
from __future__ import annotations

import html
import re
import time
from datetime import datetime, timedelta, timezone

from .. import net, remotezip

BASE = 'https://kenney.nl'
REVISIT_DAYS = 30
PAUSE = 0.6
DEFAULT_VARIANT = {kind: ['zip'] for kind in ('model', 'sprite', 'ui', 'sound', 'music', 'texture', 'hdri',
                                              'animation')}
MUSIC_WORDS = re.compile(r'\b(music|jingles?|songs?|soundtrack)\b', re.I)
UI_WORDS = re.compile(r'\b(ui|interface|icons?|cursors?|fonts?|input prompts?|crosshairs?|buttons?|game icons)\b', re.I)
UI_TAGS = {'interface', 'ui', 'gui', 'icon', 'icons', 'cursor', 'cursors', 'font', 'fonts', 'input', 'hud'}


def _text(fragment: str) -> str:
    return html.unescape(re.sub(r'<[^>]+>', ' ', fragment or '')).strip()


def parse_listing(page: str) -> tuple[list[dict], int]:
    """Pack cards on one listing page, and the highest page number linked."""
    cards = []
    for chunk in page.split("<div class='asset'>")[1:]:
        slug = re.search(r"href='https://kenney\.nl/assets/([a-z0-9-]+)'", chunk)
        if not slug:
            continue
        cover = re.search(r'background-image:url\("([^"]+)"\)', chunk)
        title = re.search(r"<h2><a [^>]*>(.*?)</a></h2>", chunk, re.S)
        category = re.search(r"/assets/category:([^'\"]+)['\"]", chunk)
        series = re.search(r"/assets/series:([^'\"]+)['\"]", chunk)
        cards.append({
            'slug': slug.group(1), 'title': _text(title.group(1)) if title else slug.group(1),
            'cover': cover.group(1) if cover and cover.group(1).startswith('https://') else None,
            'category': html.unescape(category.group(1)) if category else None,
            'series': html.unescape(series.group(1)).replace('%20', ' ') if series else None,
        })
    pages = [int(n) for n in re.findall(r"/assets/page:(\d+)['\"]", page)]
    return cards, max(pages or [1])


def _row(page: str, label: str) -> str | None:
    match = re.search(r"<td class='title text-muted'>\s*" + re.escape(label) + r"\s*</td>\s*<td[^>]*>(.*?)</td>",
                      page, re.S)
    return match.group(1) if match else None


def parse_pack(page: str, slug: str) -> dict:
    """Details from one pack page."""
    title = re.search(r'<h1[^>]*>(.*?)</h1>', page, re.S)
    tags_cell = _row(page, 'Tags') or ''
    category_cell = _row(page, 'Category') or ''
    license_cell = _row(page, 'License') or ''
    files = re.search(r'(\d[\d,]*)\s*×', _row(page, 'Files') or '')
    zips = re.findall(r"https://kenney\.nl/media/pages/assets/" + re.escape(slug) + r"/[^'\"\s]+\.zip", page)
    preview = re.search(r"class='screenshot large' href='(https://[^']+)'", page)
    sample = re.search(r"property='og:image'\s+content='(https://[^']+)'", page)
    version = re.search(r"<span class='type[^']*'>([^<]+)</span>", page)
    released = re.search(r"<td title='(\d{2})/(\d{2})/(\d{4})'>", page)
    return {
        'title': _text(title.group(1)) if title else None,
        'tags': [_text(t) for t in re.findall(r"class='tag'>(.*?)</a>", tags_cell)],
        'category': (re.findall(r"/assets/category:([^'\"]+)['\"]", category_cell) or [None])[0],
        'series': (re.findall(r"/assets/series:([^'\"]+)['\"]", category_cell) or [None])[0],
        # <span class='feature'><span>🎞️</span>Animation</span>: keep the label, drop the emoji.
        'features': [_text(f) for f in re.findall(r"<span class='feature'>(?:<span[^>]*>.*?</span>)?\s*([^<]+)</span>",
                                                  _row(page, 'Features') or '', re.S)],
        'files': int(files.group(1).replace(',', '')) if files else None,
        'license_text': _text(license_cell),
        'license_url': (re.findall(r"href='([^']+)'", license_cell) or [None])[0],
        'zip': zips[0] if zips else None,
        'preview': preview.group(1) if preview else (sample.group(1) if sample else None),
        'version': _text(version.group(1)) if version else None,
        'released': f'{released.group(3)}-{released.group(2)}-{released.group(1)}T00:00:00Z' if released else None,
    }


# Folder and file names that describe the pack's layout rather than its contents.
_LAYOUT_WORDS = set('''license preview previews sample overview readme visit kenney patreon view documentation
colormap texture textures sheet sheets spritesheet spritesheets tilesheet tilesheets tilemap tile tiles default
double vector vectors png svg models model format formats glb gltf fbx obj mtl dae stl ply blend fonts audio ogg
wav mp3 isometric side front back top bottom left right style styles extra extras misc other variation variations
ui pack kit''' .split())


def item_names(paths: list[str], limit: int = 400) -> list[str]:
    """Searchable names for what a pack contains, from its file and folder names."""
    names = set()
    for path in paths:
        parts = [p for p in path.split('/') if p]
        if not parts:
            continue
        for index, part in enumerate(parts):
            stem = part.rsplit('.', 1)[0] if index == len(parts) - 1 else part
            stem = re.sub(r'([a-z])([A-Z])', r'\1 \2', stem)
            words = [w for w in re.split(r'[^a-z]+', stem.lower()) if len(w) > 1]
            if words and not all(w in _LAYOUT_WORDS for w in words):
                names.add(' '.join(words))
    return sorted(names)[:limit]


def read_contents(zip_url: str) -> dict:
    """The pack's file list from the zip's own index (one small range request)."""
    members = remotezip.index(zip_url)
    files = [m.name for m in members if not m.name.endswith('/')]
    return {'files': files, 'contents': item_names(files)}


def classify(category: str | None, title: str, tags: list[str], series: str | None,
             features: list[str]) -> tuple[str, list[str]]:
    lowered = {t.lower() for t in tags}
    if 'skybox' in title.lower() or (series or '').lower() == 'skyboxes':
        return 'texture', ['hdri']
    if category == 'Audio':
        kind = 'music' if MUSIC_WORDS.search(title) else 'sound'
    elif category == '3D':
        kind = 'model'
    elif category == 'Textures':
        kind = 'texture'
    else:
        kind = 'sprite'
    if kind == 'sprite' and (lowered & UI_TAGS or UI_WORDS.search(title)):
        kind = 'ui'
    extra = ['animation'] if any(f.strip().lower().startswith('anim') for f in features) else []
    return kind, extra


def to_record(card: dict, pack: dict) -> dict | None:
    """One catalogue record for a pack, or None when it is not CC0."""
    license_text = (pack.get('license_text') or '').lower()
    if 'cc0' not in license_text and 'publicdomain/zero' not in (pack.get('license_url') or ''):
        return None
    title = pack.get('title') or card['title']
    category = pack.get('category') or card.get('category')
    series = (pack.get('series') or card.get('series') or '').replace('%20', ' ') or None
    tags = list(pack.get('tags') or [])
    kind, extra = classify(category, title, tags, series, pack.get('features') or [])
    pixel = 'pixel' in title.lower() or 'pixel' in {t.lower() for t in tags}
    style = 'low-poly' if kind == 'model' else ('pixel' if pixel else 'stylized' if kind in ('sprite', 'ui', 'texture')
                                                 else None)
    tags += ['kenney', 'game-ready'] + ([category.lower()] if category else []) + \
        ([series.lower()] if series else []) + (['low-poly'] if kind == 'model' else []) + \
        (['animated'] if extra else [])
    files = pack.get('files')
    zip_url = pack.get('zip')
    downloads = None
    if zip_url:
        downloads = [{'id': 'zip', 'label': 'Full pack (zip)', 'resolution': None, 'format': 'zip',
                      'archive': 'zip', 'size': None,
                      'files': [{'path': zip_url.rsplit('/', 1)[-1], 'url': zip_url, 'size': None, 'md5': None}]}]
    kind_label = {'model': '3D', 'sprite': '2D', 'ui': 'UI', 'sound': 'audio', 'music': 'music',
                  'texture': 'texture'}.get(kind, kind)
    description = (f'{title}: a free CC0 {kind_label} pack by Kenney'
                   + (f' from the {series} series' if series else '')
                   + (f', {files} files' if files else '')
                   + (', with animation' if extra else '') + '.'
                   + (' Includes GLB, FBX and OBJ versions of each model.' if kind == 'model' else ''))
    return {
        'source': 'kenney', 'source_id': card['slug'], 'type': kind, 'extra_types': extra, 'title': title,
        'description': description, 'tags': tags, 'categories': [c for c in (category, series) if c],
        'style': style, 'license': 'CC0-1.0',
        'authors': [{'name': 'Kenney', 'url': 'https://kenney.nl'}],
        'source_url': f'{BASE}/assets/{card["slug"]}', 'thumbnail_url': card.get('cover') or pack.get('preview'),
        'preview_url': pack.get('preview') or card.get('cover'),
        'formats': ['glb', 'fbx', 'obj'] if kind == 'model' else ['zip'],
        'attributes': {'pack': True, 'items': files, 'item_label': 'files', 'series': series,
                       'features': pack.get('features') or [], 'version': pack.get('version'),
                       'page_fetched_at': pack.get('fetched_at'), 'zip_url': zip_url,
                       'support_url': 'https://kenney.nl/support'},
        'downloads': downloads, 'popularity': 0.35, 'published_at': pack.get('released'),
    }


def _fresh(record: dict, days: int = REVISIT_DAYS) -> bool:
    stamp = (record.get('attributes') or {}).get('page_fetched_at')
    try:
        fetched = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
    except (AttributeError, ValueError):
        return False
    return datetime.now(timezone.utc) - fetched < timedelta(days=days)


def fetch_records(log=print, known=None, vocabulary=None, get=None, pause: float = PAUSE):
    """Every pack on kenney.nl; pages of packs seen recently are not refetched."""
    get = get or (lambda url: net.get_text(url, timeout=30))
    known = known or {}
    first = get(f'{BASE}/assets')
    cards, last = parse_listing(first)
    for number in range(2, last + 1):
        time.sleep(pause)
        more, _ = parse_listing(get(f'{BASE}/assets/page:{number}'))
        cards += more
    unique = list({card['slug']: card for card in cards}.values())
    log(f'Kenney: {len(unique)} packs listed on {last} pages.')
    fetched = indexed = 0

    def with_contents(record: dict, old: dict | None) -> dict:
        """Attach the pack's file list, reusing the stored one while the zip is unchanged."""
        nonlocal indexed
        attributes = record.setdefault('attributes', {})
        old_attributes = (old or {}).get('attributes') or {}
        zip_url = attributes.get('zip_url')
        if old_attributes.get('contents') is not None and old_attributes.get('zip_url') == zip_url:
            attributes['files'] = old_attributes.get('files') or []
            attributes['contents'] = old_attributes['contents']
            return record
        if zip_url:
            time.sleep(pause)
            try:
                attributes.update(read_contents(zip_url))
                indexed += 1
            except net.FetchError as exc:
                log(f'  Kenney {record["source_id"]}: could not read the zip index ({exc})')
        return record

    for card in unique:
        old = known.get(card['slug'])
        if old and _fresh(old):
            kind = 'music' if old['type'] == 'sound' and MUSIC_WORDS.search(old['title']) else old['type']
            yield with_contents({**old, 'type': kind, 'thumbnail_url': card.get('cover') or old.get('thumbnail_url'),
                                 'attributes': dict(old.get('attributes') or {})}, old)
            continue
        time.sleep(pause)
        try:
            pack = parse_pack(get(f'{BASE}/assets/{card["slug"]}'), card['slug'])
        except net.FetchError as exc:
            log(f'  Kenney {card["slug"]}: {exc}')
            if old:
                yield old
            continue
        pack['fetched_at'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        fetched += 1
        record = to_record(card, pack)
        if record is None:
            log(f'  Kenney {card["slug"]}: not CC0, skipped')
            continue
        old_downloads = (old or {}).get('downloads') or []
        if old_downloads and record['downloads'] and old_downloads[0]['files'][0]['url'] == record['downloads'][0]['files'][0]['url']:
            record['downloads'] = old_downloads  # same zip as before: keep its probed size
        yield with_contents(record, old)
    log(f'Kenney: fetched {fetched} pack pages (others were fresh); read {indexed} zip indexes.')


def probe_sizes(asset: dict) -> list[dict] | None:
    """Fill in a pack zip's size with one HEAD request (not listed on the site)."""
    variants = asset.get('downloads') or []
    changed = False
    for variant in variants:
        for file in variant.get('files') or []:
            if file.get('size') is None and file.get('url'):
                try:
                    file['size'] = net.head_size(file['url'])
                except net.FetchError:
                    return None
                changed = True
        if changed:
            variant['size'] = sum(f.get('size') or 0 for f in variant['files']) or None
    return variants if changed else None
