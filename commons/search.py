"""Search: natural-language queries plus structured filters.

"low-poly jungle trees, CC0, under 5k tris" is read as filters (style
low-poly, public-domain licence, max 5,000 polys) plus the concepts
"jungle" and "trees". Each concept is matched through the full-text index
with stemming, prefixes and a few close synonyms. Results that cover every
concept rank first, then title matches, then text relevance, popularity and a
small preference for public-domain assets.

Filters an agent states explicitly are always hard. Filters inferred from the
words of a query are hard too, except style and numeric limits: when those
leave nothing, they are relaxed and the response says so in `notices`.
"""
from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter

from .catalog import STYLES, TYPES, card, row_dict
from .licenses import LICENSES, filter_ids
from .sources import SOURCES

STOPWORDS = set('''a an and any are as at be by can could find for from get give good have i in into is it
its looking me my need nice of on one or please show some something that the their them these this those to
use want we which with you your free open asset assets resource resources stuff thing things kind type'''.split())

_PHRASES = [
    # (pattern, filter, value) — checked on the lower-cased query, longest first.
    (r'\bsound ?effects?\b|\bsfx\b|\bfoley\b', 'type', 'sound'),
    (r'\benvironment ?maps?\b|\benv ?maps?\b|\bsky ?box(?:es)?\b|\bhdris?\b|\bhdr\b|\bpanoramas?\b', 'type', 'hdri'),
    (r'\blow[\s-]?poly\b', 'style', 'low-poly'),
    (r'\bpixel[\s-]?art\b|\b(?:8|16)[\s-]?bit\b', 'style', 'pixel'),
    (r'\bhand[\s-]?painted\b', 'style', 'hand-painted'),
    (r'\bpublic[\s-]domain\b|\bno attribution\b|\bcc[\s-]?0\b|\bcc[\s-]?zero\b', 'license', 'public-domain'),
    (r'\bcc[\s-]?by[\s-]?sa\b|\bshare[\s-]?alike\b', 'license', 'share-alike'),
    (r'\bcc[\s-]?by\b', 'license', 'attribution'),
    (r'\bpoly ?haven\b', 'source', 'polyhaven'),
    (r'\bambient ?cg\b', 'source', 'ambientcg'),
    (r'\bopen ?game ?art\b', 'source', 'opengameart'),
]
_WORDS = {
    'type': {
        'texture': 'texture', 'textures': 'texture', 'material': 'texture', 'materials': 'texture',
        'pbr': 'texture', 'decal': 'texture', 'decals': 'texture', 'surface': 'texture', 'surfaces': 'texture',
        'model': 'model', 'models': 'model', 'mesh': 'model', 'meshes': 'model', '3d': 'model',
        'prop': 'model', 'props': 'model', 'gltf': 'model', 'glb': 'model', 'fbx': 'model',
        'sound': 'sound', 'sounds': 'sound', 'audio': 'sound', 'ambience': 'sound',
        'music': 'music', 'musical': 'music', 'song': 'music', 'songs': 'music', 'soundtrack': 'music',
        'soundtracks': 'music', 'bgm': 'music', 'tune': 'music', 'tunes': 'music', 'melody': 'music',
        'melodies': 'music', 'jingle': 'music', 'jingles': 'music',
        'animation': 'animation', 'animations': 'animation', 'anim': 'animation', 'anims': 'animation',
        'mocap': 'animation', 'rigged': 'animation', 'animated': 'animation',
        '2d': 'sprite', 'sprite': 'sprite', 'sprites': 'sprite', 'spritesheet': 'sprite',
        'spritesheets': 'sprite', 'tileset': 'sprite', 'tilesets': 'sprite', 'tilemap': 'sprite',
        'ui': 'ui', 'gui': 'ui', 'hud': 'ui', 'interface': 'ui', 'icon': 'ui', 'icons': 'ui',
        'button': 'ui', 'buttons': 'ui', 'font': 'ui', 'fonts': 'ui', 'cursor': 'ui', 'cursors': 'ui',
    },
    'style': {
        'lowpoly': 'low-poly', 'stylized': 'stylized', 'stylised': 'stylized', 'cartoon': 'stylized',
        'cartoony': 'stylized', 'toon': 'toon', 'cel': 'toon', 'realistic': 'realistic',
        'photoreal': 'realistic', 'photorealistic': 'realistic', 'photoscanned': 'realistic',
        'scanned': 'realistic', 'pixel': 'pixel', 'pixelart': 'pixel',
    },
    'source': {source: source for source in SOURCES} | {'kenney': 'kenney', 'quaternius': 'quaternius',
                                                         'freesound': 'freesound', 'oga': 'opengameart'},
}
_FORMAT_WORDS = {'gltf': 'gltf', 'glb': 'gltf', 'fbx': 'fbx'}
# Words that mean "help me make one" rather than describing the asset.
MAKE_WORDS = {'generate', 'generated', 'generating', 'generator', 'generators', 'create', 'creating', 'make',
              'making', 'ai', 'custom', 'bespoke', 'tool', 'tools'}
# Specific nouns that set a type and are also worth searching for ("font", not "ui").
_ALSO_CONCEPT = {'font', 'fonts', 'icon', 'icons', 'button', 'buttons', 'cursor', 'cursors', 'crosshair',
                 'crosshairs', 'tileset', 'tilesets', 'spritesheet', 'spritesheets', 'tilemap', 'decal', 'decals',
                 'hud', 'prop', 'props', 'ambience', 'jingle', 'jingles', 'mocap'}
# Words that make a query about audio, where "8-bit" names a music style, not pixel art.
_AUDIO_WORDS = re.compile(r'\b(music\w*|songs?|soundtracks?|bgm|tunes?|melod\w+|jingles?|chiptunes?|sounds?|sfx|'
                          r'audio|ambience|loops?)\b')
_BIT_STYLE = re.compile(r'\b(?:8|16)[\s-]?bit\b')
# Words that make sky photos (HDRIs) a sensible answer.
SCENE_WORDS = {'sky', 'skies', 'skybox', 'hdri', 'hdr', 'sunset', 'sunrise', 'dusk', 'dawn', 'night', 'cloud',
               'clouds', 'cloudy', 'overcast', 'studio', 'lighting', 'light', 'environment', 'panorama', 'outdoor',
               'indoor', 'interior', 'landscape', 'scene', 'horizon', 'sun', 'moon', 'stars', 'storm', 'fog'}

SYNONYMS = {
    'jungle': ['tropical', 'rainforest'], 'rainforest': ['jungle'], 'tropical': ['jungle'],
    'forest': ['woodland'], 'rock': ['stone', 'boulder'], 'stone': ['rock'],
    'boulder': ['rock'], 'ground': ['soil', 'dirt', 'terrain'], 'dirt': ['soil', 'mud'],
    'soil': ['dirt'], 'mud': ['dirt', 'muddy'], 'wood': ['wooden', 'timber', 'plank'],
    'wooden': ['wood'], 'metal': ['metallic', 'steel', 'iron'], 'steel': ['metal'], 'iron': ['metal'],
    'grass': ['lawn', 'meadow'], 'sea': ['ocean'], 'ocean': ['sea'], 'car': ['vehicle'],
    'vehicle': ['car', 'truck'], 'house': ['building'], 'building': ['house', 'architecture'],
    'cloudy': ['overcast'], 'overcast': ['cloudy'], 'night': ['nighttime', 'moonlight'],
    'sunset': ['dusk'], 'dusk': ['sunset'], 'sunrise': ['dawn'], 'dawn': ['sunrise'],
    'indoor': ['interior'], 'interior': ['indoor'], 'outdoor': ['exterior'], 'exterior': ['outdoor'],
    'sofa': ['couch'], 'couch': ['sofa'], 'chair': ['seat'], 'snow': ['snowy', 'winter'],
    'winter': ['snow', 'snowy'], 'desert': ['sand', 'arid'], 'sand': ['sandy'], 'fabric': ['cloth', 'textile'],
    'cloth': ['fabric'], 'concrete': ['cement'], 'asphalt': ['road', 'tarmac'], 'road': ['asphalt'],
    'bush': ['shrub'], 'shrub': ['bush'], 'plant': ['vegetation', 'foliage'], 'foliage': ['leaves', 'plant'],
    'brick': ['bricks', 'masonry'], 'tile': ['tiles', 'tiled'], 'floor': ['flooring'],
    'explosion': ['blast'], 'footstep': ['footsteps'], 'sci-fi': ['scifi', 'futuristic'],
    'campfire': ['bonfire', 'fireplace'], 'bonfire': ['campfire'], 'pickup': ['collectible', 'powerup'],
    'gun': ['firearm', 'pistol', 'rifle', 'blaster'], 'weapon': ['weapons', 'sword', 'axe', 'gun', 'blaster'],
    'character': ['person', 'people', 'humanoid', 'npc'], 'person': ['character', 'human'],
    'enemy': ['monster', 'creature'], 'monster': ['creature', 'enemy'], 'boat': ['ship'], 'ship': ['boat'],
    'plane': ['aircraft', 'airplane'], 'spaceship': ['rocket', 'starship'], 'castle': ['fortress'],
    'dog': ['puppy'], 'crate': ['box'], 'box': ['crate'], 'potion': ['flask', 'bottle'], 'magic': ['spell'],
    'coin': ['coins'], 'heart': ['hearts'], 'key': ['keys'], 'gem': ['gems', 'crystal'], 'arrow': ['arrows'],
    'scifi': ['sci-fi', 'futuristic'], 'medieval': ['castle'], 'ruin': ['ruins', 'ruined'],
    # Music and sound moods.
    'chiptune': ['8-bit', 'chiptunes', 'chip', 'nes', 'retro'], 'loop': ['loopable', 'looping', 'loops'],
    'loopable': ['loop', 'looping'], 'battle': ['combat', 'fight', 'boss'], 'boss': ['battle'],
    'calm': ['peaceful', 'relaxing', 'ambient'], 'peaceful': ['calm', 'relaxing'], 'relaxing': ['calm', 'peaceful'],
    'happy': ['upbeat', 'cheerful'], 'upbeat': ['happy', 'energetic'], 'cheerful': ['happy', 'upbeat'],
    'sad': ['melancholy', 'melancholic'], 'melancholy': ['sad', 'melancholic'],
    'scary': ['horror', 'creepy', 'spooky'], 'horror': ['scary', 'creepy', 'spooky'], 'creepy': ['horror', 'spooky'],
    'spooky': ['creepy', 'horror'], 'epic': ['orchestral', 'cinematic'], 'orchestral': ['orchestra', 'cinematic'],
    'victory': ['fanfare', 'win'], 'fanfare': ['victory'],
}

_RESOLUTION = re.compile(r'\b(1|2|4|8|16)\s?k\b')
_MAX_POLYS = re.compile(r'(?:under|below|less than|fewer than|max(?:imum)?|at most|up to|<|≤)\s*'
                        r'(\d+(?:[.,]\d+)?)\s*(k)?\s*(?:tris|triangles|polys|polygons|poly|faces)\b')
_MAX_SECONDS = re.compile(r'(?:under|shorter than|less than|at most|<|≤)\s*(\d+(?:\.\d+)?)\s*'
                          r'(?:s|sec|secs|seconds)\b')
_TOKEN = re.compile(r"[a-z0-9][a-z0-9'-]*")

SORTS = ('relevance', 'popular', 'newest', 'name')
# Inferred limits (style, numbers) that leave fewer results than this are relaxed: the strict
# matches come first and other close matches follow, so "stylized forest" is not two packs.
FEW_STRICT = 6


def _as_list(value) -> list[str]:
    if value is None or value == '':
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(',') if part.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(part).strip() for part in value if str(part).strip()]
    return [str(value)]


def parse_query(text: str) -> dict:
    """Split a natural-language query into concepts and inferred filters."""
    text = (text or '').lower()
    inferred: dict[str, set] = {'type': set(), 'style': set(), 'license': set(), 'source': set(),
                                'format': set()}
    numbers: dict[str, float] = {}
    match = _MAX_POLYS.search(text)
    if match:
        value = float(match.group(1).replace(',', '.'))
        numbers['max_polycount'] = int(value * (1000 if match.group(2) else 1))
        text = text[:match.start()] + ' ' + text[match.end():]
    match = _MAX_SECONDS.search(text)
    if match:
        numbers['max_duration'] = float(match.group(1))
        text = text[:match.start()] + ' ' + text[match.end():]
    match = _RESOLUTION.search(text)
    if match:
        numbers['min_resolution'] = int(match.group(1)) * 1000
        text = text[:match.start()] + ' ' + text[match.end():]
    if _AUDIO_WORDS.search(text):  # "8-bit music" is chiptune, not pixel art
        text = _BIT_STYLE.sub(' chiptune ', text)
    for pattern, key, value in _PHRASES:
        if re.search(pattern, text):
            inferred[key].add(value)
            if re.search(r'\bsky ?box', text):
                text += ' sky'  # a skybox request is also a search for skies
            text = re.sub(pattern, ' ', text)
    terms: list[str] = []
    intent = None
    for token in _TOKEN.findall(text):
        token = token.strip("'-")
        if token in MAKE_WORDS:
            intent = 'make'
            continue
        if token in _FORMAT_WORDS:
            inferred['format'].add(_FORMAT_WORDS[token])
        hit = False
        for key, words in _WORDS.items():
            if token in words:
                inferred[key].add(words[token])
                hit = True
        if (hit and token not in _ALSO_CONCEPT) or token in STOPWORDS or len(token) < 2:
            continue
        if token not in terms:
            terms.append(token)
    return {'terms': terms[:12], 'filters': {k: sorted(v) for k, v in inferred.items() if v},
            'numbers': numbers, 'intent': intent}


def _group(term: str) -> list[str]:
    words = [term] + SYNONYMS.get(term, [])
    return [w for w in dict.fromkeys(words) if re.fullmatch(r"[a-z0-9][a-z0-9'-]*", w)]


def _fts_expr(words: list[str]) -> str:
    parts = []
    for word in words:
        pieces = [p for p in re.split(r"[-']", word) if p]
        if len(pieces) > 1:
            parts.append('"' + ' '.join(pieces) + '"')
        elif len(pieces[0]) >= 4:
            parts.append(f'"{pieces[0]}"*')
        else:  # short words match exactly (stemmed): "bow" must not find "bowl"
            parts.append(f'"{pieces[0]}"')
    return '(' + ' OR '.join(parts) + ')'


def _matches(db: sqlite3.Connection, expr: str, column: str | None = None) -> dict[int, float]:
    query = f'{{{column}}} : {expr}' if column else expr
    rows = db.execute('SELECT rowid, bm25(assets_fts, 8.0, 5.0, 3.0, 1.0, 0.5, 0.5, 2.0) FROM assets_fts '
                      'WHERE assets_fts MATCH ?', (query,)).fetchall()
    return {row[0]: row[1] for row in rows}


_LIGHT = ('SELECT rowid, id, type, extra_types, license, source, style, polycount, max_resolution, duration, '
          'formats, lower(tags) AS tags_l, lower(categories) AS cats_l, popularity, published_at, title, status '
          'FROM assets')


def search(db: sqlite3.Connection, query: str = '', *, type=None, license=None, source=None, style=None,
           tags=None, category=None, format=None, min_resolution=None, max_polycount=None,
           max_duration=None, sort: str | None = None, limit: int = 24, offset: int = 0,
           status: str = 'published', facets: bool = True) -> dict:
    query = (query or '').strip()[:300]
    limit = max(1, min(int(limit or 24), 100))
    offset = max(0, int(offset or 0))
    exact = None
    if re.fullmatch(r'[a-z][a-z0-9-]{1,31}:[A-Za-z0-9._~-]{1,160}', query):
        exact = db.execute('SELECT rowid FROM assets WHERE id=?', (query,)).fetchone()
    parsed = parse_query('' if exact else query)
    explicit = {
        'type': [t for t in _as_list(type) if t in TYPES],
        'style': [s for s in _as_list(style) if s in STYLES],
        'source': [s.lower() for s in _as_list(source)],
        'format': [f.lower() for f in _as_list(format)],
    }
    explicit_license = filter_ids(_as_list(license))
    if _as_list(license) and not explicit_license:
        explicit_license = {'__none__'}
    inferred = parsed['filters']
    license_ids = explicit_license or (filter_ids(inferred.get('license', [])) if inferred.get('license') else set())
    hard = {
        'type': set(explicit['type'] or inferred.get('type', [])),
        'source': set(explicit['source'] or inferred.get('source', [])),
        'format': set(explicit['format'] or inferred.get('format', [])),
        'license': license_ids,
    }
    soft = {}  # inferred filters that may be relaxed
    style_set = set(explicit['style'])
    if not style_set and inferred.get('style'):
        soft['style'] = set(inferred['style'])
    numbers = {'min_resolution': _num(min_resolution), 'max_polycount': _num(max_polycount),
               'max_duration': _num(max_duration)}
    for key, value in parsed['numbers'].items():
        if numbers.get(key) is None:
            soft[key] = value
    want_tags = [t.lower() for t in _as_list(tags)]
    want_cats = [c.lower() for c in _as_list(category)]

    # Concepts → candidate rows with text scores.
    groups = [_group(term) for term in parsed['terms']]
    scores: dict[int, float] = {}
    coverage: Counter = Counter()   # concepts matched, by the word or a synonym
    exact_cov: Counter = Counter()  # concepts matched by the word itself
    title_cov: Counter = Counter()  # concepts whose word appears in the title
    if groups:
        for words in groups:
            expr = _fts_expr(words)
            hits = _matches(db, expr)
            for rowid, rank in hits.items():
                coverage[rowid] += 1
                scores[rowid] = scores.get(rowid, 0.0) + (-rank)
            exact_expr = _fts_expr(words[:1])
            for rowid in (_matches(db, exact_expr) if len(words) > 1 else hits):
                exact_cov[rowid] += 1
            for rowid in _matches(db, exact_expr, 'title'):
                title_cov[rowid] += 1
        candidate_ids = set(scores)
    statuses = ('published',) if status == 'published' else tuple(_as_list(status)) or ('published',)
    sql = _LIGHT + f' WHERE status IN ({",".join("?" for _ in statuses)})'
    if exact:
        rows = [dict(r) for r in db.execute(sql + ' AND rowid=?', (*statuses, exact[0]))]
    elif groups:  # only the rows the text matched
        rows = [dict(r) for r in db.execute(sql + ' AND rowid IN (SELECT value FROM json_each(?))',
                                            (*statuses, json.dumps(sorted(candidate_ids))))]
    else:
        rows = [dict(r) for r in db.execute(sql, statuses)]
    for row in rows:
        extra = row['extra_types']
        row['types'] = {row['type']} if not extra or extra == '[]' else {row['type'], *json.loads(extra)}

    def failures(row, use_soft=True) -> frozenset:
        """The filters a row fails: 'type', 'license', 'source', 'style', or 'other' (never relaxed for facets)."""
        failed = set()
        if hard['type'] and not row['types'] & hard['type']:
            failed.add('type')
        if hard['license'] and row['license'] not in hard['license']:
            failed.add('license')
        if hard['source'] and row['source'] not in hard['source']:
            failed.add('source')
        styles = style_set or (soft.get('style') if use_soft else None)
        if styles and row['style'] not in styles and not any(f'"{style}"' in row['tags_l'] for style in styles):
            failed.add('style')
        if hard['format'] and not any(f'"{f}"' in (row['formats'] or '').lower()
                                      or (f == 'gltf' and '"glb"' in (row['formats'] or '').lower())
                                      for f in hard['format']):
            failed.add('other')
            return frozenset(failed)
        limits = limits_soft if use_soft else limits_hard
        if 'min_resolution' in limits and (row['max_resolution'] or 0) < limits['min_resolution'] \
                and row['type'] in ('texture', 'hdri', 'model'):
            failed.add('other')
        elif 'max_polycount' in limits and row['type'] == 'model' and \
                (row['polycount'] is None or row['polycount'] > limits['max_polycount']):
            failed.add('other')
        elif 'max_duration' in limits and row['type'] in ('sound', 'music', 'animation') and \
                (row['duration'] is None or row['duration'] > limits['max_duration']):
            failed.add('other')
        elif want_tags and not all(f'"{t}"' in row['tags_l'] for t in want_tags):
            failed.add('other')
        elif want_cats and not all(f'"{c}"' in row['cats_l'] for c in want_cats):
            failed.add('other')
        return frozenset(failed)

    limits_hard = {k: v for k, v in numbers.items() if v is not None}
    limits_soft = {**limits_hard, **{k: soft[k] for k in ('min_resolution', 'max_polycount', 'max_duration')
                                     if k in soft}}
    notices = []
    failed = [failures(r) for r in rows]
    matched = [r for r, f in zip(rows, failed) if not f]
    soft_used = soft
    strict: set[int] = set()  # rows that met the inferred limits too; they stay first
    if soft and len(matched) < FEW_STRICT:
        failed_hard = [failures(r, use_soft=False) for r in rows]
        relaxed = [r for r, f in zip(rows, failed_hard) if not f]
        if len(relaxed) > len(matched):
            dropped = ', '.join(_soft_label(k, v) for k, v in soft.items())
            notices.append(f'Only {len(matched)} matched {dropped}; other close matches follow them.' if matched
                           else f'Nothing matched {dropped}; showing the closest matches without that limit.')
            strict = {r['rowid'] for r in matched}
            matched = relaxed
            failed = failed_hard
            soft_used = {}

    order = sort if sort in SORTS else ('relevance' if groups else 'popular')
    scene_query = any(word in SCENE_WORDS for group in groups for word in group)
    n_groups = max(1, len(groups))

    def score(row):
        rid = row['rowid']
        value = 0.0
        if groups:
            value += (100.0 * coverage[rid] + 25.0 * exact_cov[rid] + 20.0 * title_cov[rid]) / n_groups
            value += min(scores.get(rid, 0.0), 30.0)
        value += 8.0 * (row['popularity'] or 0.0)
        if groups and row['type'] == 'hdri' and 'hdri' not in hard['type'] and not scene_query:
            value -= 30.0  # an HDRI tagged "dog" is a photo with a dog in it, not a dog asset
        if LICENSES.get(row['license']) and LICENSES[row['license']].tier == 'public-domain':
            value += 3.0
        return value

    if order == 'relevance':
        matched.sort(key=lambda r: (-score(r), r['title'].lower()))
    elif order == 'popular':
        matched.sort(key=lambda r: (-(r['popularity'] or 0.0), r['title'].lower()))
    elif order == 'newest':
        matched.sort(key=lambda r: (r['published_at'] or ''), reverse=True)
    else:
        matched.sort(key=lambda r: r['title'].lower())
    if strict:  # the few that met every inferred limit first, in the chosen order (sort is stable)
        matched.sort(key=lambda r: r['rowid'] not in strict)
    total = len(matched)
    page = matched[offset:offset + limit]
    results = []
    if page:
        marks = ','.join('?' for _ in page)
        full = {row['rowid']: row_dict(row) for row in db.execute(
            f'SELECT rowid, * FROM assets WHERE rowid IN ({marks})', [r['rowid'] for r in page])}
        for r in page:
            asset = full[r['rowid']]
            item = card(asset)
            if groups:
                item['match'] = round(coverage[r['rowid']] / n_groups, 2)
                contents = (asset.get('attributes') or {}).get('contents') or []
                if contents:
                    words = [w for group in groups for w in group]
                    hits = [name for name in contents
                            if any(re.search(r'(^|\s)' + re.escape(w.rstrip('s')), name) for w in words)]
                    if hits:
                        item['matched_items'] = hits[:8]
            results.append(item)

    facet_counts = {}
    if facets:
        for key in ('type', 'license', 'source', 'style'):
            counter = Counter()
            allowed = {frozenset(), frozenset({key})}  # rows that pass every filter except this facet's own
            for row, fails in zip(rows, failed):
                if fails in allowed:
                    if key == 'type':  # an asset counts under each of its roles
                        counter.update(row['types'])
                        continue
                    value = row[key]
                    if key == 'license':
                        value = LICENSES[value].tier if value in LICENSES else 'unknown'
                    counter[value or 'unspecified'] += 1
            facet_counts[key] = dict(counter.most_common())

    interpreted = {'concepts': [g[0] for g in groups], 'synonyms': {g[0]: g[1:] for g in groups if len(g) > 1}}
    if parsed.get('intent'):
        interpreted['intent'] = parsed['intent']
    for key in ('type', 'source', 'format'):
        if hard[key]:
            interpreted[key] = sorted(hard[key])
    if license_ids:
        interpreted['license'] = sorted(license_ids)
    if style_set or soft_used.get('style'):
        interpreted['style'] = sorted(style_set or soft_used['style'])
    for key in ('min_resolution', 'max_polycount', 'max_duration'):
        value = numbers.get(key) if numbers.get(key) is not None else soft_used.get(key)
        if value is not None:
            interpreted[key] = value
    if order:
        interpreted['sort'] = order
    if total == 0:
        notices.append(_empty_hint(hard, style_set or soft.get('style')))
    return {
        'total': total, 'offset': offset, 'limit': limit,
        'next_offset': offset + limit if offset + limit < total else None,
        'results': results, 'facets': facet_counts, 'interpreted': interpreted,
        'notices': [n for n in notices if n],
    }


def _num(value):
    try:
        return float(value) if value not in (None, '') else None
    except (TypeError, ValueError):
        return None


def _soft_label(key, value):
    if key == 'style':
        return 'the ' + '/'.join(sorted(value)) + ' style'
    if key == 'min_resolution':
        return f'{int(value) // 1000}K resolution'
    if key == 'max_polycount':
        return f'under {int(value):,} polys'
    if key == 'max_duration':
        return f'under {value:g} s'
    return key


def _empty_hint(hard, styles) -> str:
    kinds = hard.get('type') or set()
    if 'animation' in kinds:
        return 'No animations matched. Try “animated character” or a creature, vehicle or weapon.'
    if 'sound' in kinds:
        return 'No CC0 sounds matched. Try other words.'
    if 'music' in kinds:
        return 'No music matched. Try a mood or genre (“calm”, “battle”, “chiptune”, “orchestral”) or fewer words.'
    if styles and styles & {'low-poly', 'stylized', 'pixel', 'toon', 'hand-painted'}:
        return 'Nothing in that style matched. Kenney and Quaternius packs are the stylized and low-poly sources.'
    return ('No assets match. Try fewer words, a broader type, or remove a filter; the tools listed with these '
            'results can generate what the library lacks.')
