"""Quaternius importer (https://quaternius.com): CC0 low-poly packs, one entry per pack.

The home page lists every pack (title, thumbnail, public tags and a run-together
keyword string); each pack page adds its description, model count, whether it
is animated or textured, formats and licence. Requests are paced and a pack
page is revisited at most every REVISIT_DAYS.

Quaternius distributes the files through itch.io's pay-what-you-want page
(short-lived links after a checkout step) or, for older packs, Google Drive
folders. Asset Commons automates neither, so these packs have no automatic
download: people and agents get the real link (free) and the pack's details.
"""
from __future__ import annotations

import html
import re
import time
from datetime import datetime, timedelta, timezone

from .. import net

BASE = 'https://quaternius.com'
REVISIT_DAYS = 30
PAUSE = 0.6
DEFAULT_VARIANT: dict = {}
# Words the run-together keyword strings are split into (with the library's tags).
BASE_WORDS = set('''game kit gamekit unreal engine godot unity alien aliens atmospheric scifi sci fi scary spooky
environment modular fantasy ghibli farming farm nature tree trees bush bushes flower flowers rock rocks plant plants
stylized grass mushroom mushrooms birch pine cherry medieval village castle weapon weapons sword swords axe bow
character characters animal animals vehicle vehicles car cars truck food furniture building buildings city town
dungeon monster monsters zombie zombies robot robots mech mechs space ship ships spaceship spaceships pirate
pirates train trains gun guns rifle pistol armor armour knight knights survival tank tanks fish dinosaur dinosaurs
man men woman women human humans people enemy enemies boss turret turrets ocean sea island desert snow winter
forest jungle tropical cyberpunk futuristic street streets road roads platformer platform rpg shooter toon
cartoon cute low poly lowpoly animated animation animations rigged props prop interior house houses kitchen
restaurant sushi junk transport bus taxi card cards hero heroes wizard mage archer warrior viking skeleton
undead orc goblin dragon pet pets cat dog horse cow pig sheep chicken bird birds insect insects crystal crystals
gem gems coin coins chest treasure potion potions tool tools crate crates barrel barrels fence fences wall walls
door doors window windows bridge tower towers temple ruins ruin cave caves mountain mountains water lava ice'''
                 .split())


def _text(fragment: str) -> str:
    return html.unescape(re.sub(r'<[^>]+>', ' ', fragment or '')).strip()


def segment(blob: str, vocabulary: set[str]) -> list[str]:
    """Split a run-together keyword string ("treesbushesrocks") into known words."""
    blob = re.sub(r'[^a-z]', '', (blob or '').lower())
    words, i = [], 0
    longest = max((len(w) for w in vocabulary), default=0)
    while i < len(blob):
        for size in range(min(longest, len(blob) - i), 2, -1):
            if blob[i:i + size] in vocabulary:
                words.append(blob[i:i + size])
                i += size
                break
        else:
            i += 1
    return list(dict.fromkeys(words))


def parse_home(page: str) -> list[dict]:
    packs = []
    for chunk in page.split('<div class="pack">')[1:]:
        slug = re.search(r'href="/packs/([a-z0-9-]+)\.html"', chunk)
        if not slug:
            continue
        thumb = re.search(r'src="(/assets/images/thumbnails/[^"]+)"', chunk)
        title = re.search(r'<div class="PackText">(.*?)<!--TITLE', chunk, re.S)
        hidden = re.search(r'<noscript>(.*?)</noscript>', chunk, re.S)
        packs.append({
            'slug': slug.group(1),
            'title': _text(title.group(1)) if title else slug.group(1),
            'thumbnail': BASE + thumb.group(1) if thumb else None,
            'tags': [_text(t) for t in re.findall(r'<div class="viewtag tags">(.*?)</div>', chunk, re.S)],
            'keywords': _text(hidden.group(1)) if hidden else '',
        })
    return list({p['slug']: p for p in packs}.values())


def _info(page: str, label: str) -> str | None:
    match = re.search(r'class="iconBig">\s*' + re.escape(label) + r'(.*?)</div>\s*</div>', page, re.S)
    return match.group(1) if match else None


def parse_pack(page: str, slug: str) -> dict:
    description = re.search(r'name="description"\s+content="(.*?)"\s*/?>', page, re.S)
    models = re.search(r'class="iconBig">\s*Models\s*<div class="text-right">\s*(\d+)', page)
    animated = _info(page, 'Animated') or ''
    textured = _info(page, 'Textured') or ''
    formats_block = re.search(r'class="iconBig">\s*Formats(.*?)<div class="infoitem">', page, re.S)
    license_block = re.search(r'class="iconBig">\s*License(.*?)</div></div>', page, re.S)
    # Newer pages link itch.io; some only name the itch.io game in the buy button; older ones share a
    # Google Drive folder.
    itch = re.search(r"https://quaternius\.itch\.io/[a-z0-9-]+", page)
    game = re.search(r'game:\s*"([a-z0-9-]+)"', page)
    drive = re.search(r'https://drive\.google\.com/drive/folders/[A-Za-z0-9_-]+', page)
    image = re.search(r'property="og:image"\s+content="([^"]+)"', page)
    video = re.search(r'src="(https://www\.youtube\.com/embed/[^"?]+)', page)
    title = re.search(r'<title>\s*Quaternius\s*•\s*(.*?)</title>', page, re.S)
    return {
        'title': _text(title.group(1)) if title else None,
        'description': re.sub(r'\s+', ' ', _text(description.group(1))) if description else '',
        'models': int(models.group(1)) if models else None,
        'animated': 'check-solid' in animated,
        'textured': 'check-solid' in textured,
        'formats': [_text(f).lower() for f in re.findall(r'<div class="text-right tags">(.*?)</div>',
                                                          formats_block.group(1) if formats_block else '')],
        'license_text': _text(license_block.group(1)) if license_block else '',
        'license_url': (re.findall(r'href="([^"]+)"', license_block.group(1)) or [None])[0] if license_block else None,
        'itch': itch.group(0) if itch else (f'https://quaternius.itch.io/{game.group(1)}' if game else None),
        'drive': drive.group(0) if drive else None,
        'image': (BASE + image.group(1)) if image and image.group(1).startswith('/') else (image.group(1) if image else None),
        'video': video.group(1) if video else None,
    }


def to_record(card: dict, pack: dict, vocabulary: set[str]) -> dict | None:
    if 'cc0' not in (pack.get('license_text') or '').lower() and \
            'publicdomain/zero' not in (pack.get('license_url') or ''):
        return None
    title = pack.get('title') or card['title']
    words = segment(card.get('keywords', ''), vocabulary | BASE_WORDS)
    animation_pack = bool(re.search(r'\banimation(s)?\b', title, re.I))
    kind = 'animation' if animation_pack else 'model'
    extra = ['model'] if animation_pack else (['animation'] if pack.get('animated') else [])
    stylized = 'stylized' in title.lower() or 'stylized' in words
    tags = list(card.get('tags') or []) + ['quaternius', 'low-poly', 'game-ready'] + \
        (['stylized'] if stylized else []) + (['animated', 'rigged'] if pack.get('animated') or animation_pack else []) + \
        (['textured'] if pack.get('textured') else [])
    formats = [{'gltf': 'gltf', 'glb': 'glb', 'fbx': 'fbx', 'obj': 'obj', 'blend': 'blend'}.get(f, f)
               for f in pack.get('formats') or []]
    description = pack.get('description') or f'{title}: a free CC0 low-poly pack by Quaternius.'
    if words:
        description += ' Keywords: ' + ', '.join(words) + '.'
    page_url = f'{BASE}/packs/{card["slug"]}.html'
    if pack.get('itch'):
        manual = {'url': pack['itch'], 'label': 'Free on itch.io (pay what you want)',
                  'note': 'Quaternius hands out pack files through itch.io; download the zip there (choose “No thanks, '
                          'just take me to the downloads”), then unzip it into your project.'}
    elif pack.get('drive'):
        manual = {'url': pack['drive'], 'label': 'Free on Google Drive',
                  'note': 'This pack is shared as a Google Drive folder; use “Download all” there, then unzip it '
                          'into your project.'}
    else:
        manual = {'url': page_url, 'label': 'Free on quaternius.com',
                  'note': 'Use the download button on the pack page, then unzip it into your project.'}
    return {
        'source': 'quaternius', 'source_id': card['slug'], 'type': kind, 'extra_types': extra, 'title': title,
        'description': description, 'tags': tags, 'categories': [t for t in card.get('tags') or []][:4],
        'style': 'stylized' if stylized else 'low-poly', 'license': 'CC0-1.0',
        'authors': [{'name': 'Quaternius', 'url': 'https://quaternius.com'}],
        'source_url': page_url,
        'thumbnail_url': card.get('thumbnail') or pack.get('image'),
        'preview_url': pack.get('image') or card.get('thumbnail'),
        'formats': formats,
        'attributes': {'pack': True, 'items': pack.get('models'), 'item_label': 'models',
                       'animated': bool(pack.get('animated') or animation_pack),
                       'textured': pack.get('textured'), 'video': pack.get('video'),
                       'page_fetched_at': pack.get('fetched_at'),
                       'manual_download': manual,
                       'support_url': 'https://www.patreon.com/quaternius'},
        'downloads': [], 'popularity': 0.35,
    }


def _fresh(record: dict, days: int = REVISIT_DAYS) -> bool:
    stamp = (record.get('attributes') or {}).get('page_fetched_at')
    try:
        fetched = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
    except (AttributeError, ValueError):
        return False
    return datetime.now(timezone.utc) - fetched < timedelta(days=days)


def fetch_records(log=print, known=None, vocabulary=None, get=None, pause: float = PAUSE):
    get = get or (lambda url: net.get_text(url, timeout=30))
    known = known or {}
    vocabulary = {w for w in (vocabulary or set()) if 3 <= len(w) <= 20 and w.isalpha()}
    cards = parse_home(get(f'{BASE}/'))
    log(f'Quaternius: {len(cards)} packs listed.')
    fetched = 0
    for card in cards:
        old = known.get(card['slug'])
        if old and _fresh(old):
            yield old
            continue
        time.sleep(pause)
        try:
            pack = parse_pack(get(f'{BASE}/packs/{card["slug"]}.html'), card['slug'])
        except net.FetchError as exc:
            log(f'  Quaternius {card["slug"]}: {exc}')
            if old:
                yield old
            continue
        pack['fetched_at'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        fetched += 1
        record = to_record(card, pack, vocabulary)
        if record is None:
            log(f'  Quaternius {card["slug"]}: not CC0, skipped')
            continue
        yield record
    log(f'Quaternius: fetched {fetched} pack pages (others were fresh).')
