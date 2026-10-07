"""ambientCG importer (https://ambientcg.com, all assets CC0).

The v2 `full_json` feed includes previews, tags, sizes and every zip download,
so one paged pass captures the whole catalogue with its download listings.
Materials, decals, atlases and terrains become textures; HDRIs stay HDRIs.
"""
from __future__ import annotations

import math
import re
from datetime import datetime

from .. import net

FEED = ('https://ambientcg.com/api/v2/full_json?include=downloadData,previewData,tagData,displayData,'
        'dimensionsData&sort=Popular&limit={limit}&offset={offset}')
PAGE = 250
TYPES = {'Material': 'texture', 'Decal': 'texture', 'Atlas': 'texture', 'Terrain': 'texture',
         'PlainTexture': 'texture', 'HDRI': 'hdri'}
MAP_NAMES = {'color': 'color', 'normalgl': 'normal_gl', 'normaldx': 'normal_dx', 'roughness': 'roughness',
             'ambientocclusion': 'ao', 'displacement': 'displacement', 'metalness': 'metalness',
             'opacity': 'opacity', 'emission': 'emission'}


def _iso(text) -> str | None:
    try:
        return datetime.strptime(text, '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%dT%H:%M:%SZ')
    except (TypeError, ValueError):
        return None


def _preview(images: dict, size: int) -> str | None:
    for key in (f'{size}-WEBP', f'{size}-JPG-242424', f'{size}-PNG'):
        if isinstance(images.get(key), str):
            return images[key]
    return None


def _variants(asset: dict, kind: str) -> list[dict]:
    variants = []
    folders = (asset.get('downloadFolders') or {}).get('default') or {}
    for category in (folders.get('downloadFiletypeCategories') or {}).values():
        for item in category.get('downloads') or []:
            attribute = str(item.get('attribute') or '')
            url = item.get('fullDownloadPath') or item.get('downloadLink')
            if not isinstance(url, str) or not re.fullmatch(r'[A-Za-z0-9._-]{1,120}', item.get('fileName') or ''):
                continue
            match = re.match(r'(\d+)K(?:-(\w+))?', attribute, re.I)
            res = f'{match.group(1)}k' if match else None
            fmt = (match.group(2) or ('exr' if kind == 'hdri' else 'zip')).lower() if match else attribute.lower()
            variants.append({
                'id': f'{res}-{fmt}' if res else re.sub(r'[^a-z0-9-]+', '-', attribute.lower()) or 'zip',
                'label': f'{res.upper()} {fmt.upper()} (zip)' if res else f'{attribute} (zip)',
                'resolution': res, 'format': fmt, 'archive': 'zip', 'size': item.get('size'),
                'files': [{'path': item['fileName'], 'url': url, 'size': item.get('size'), 'md5': None}],
            })
    order = {'jpg': 0, 'png': 1, 'exr': 2, 'hdr': 3}
    variants.sort(key=lambda v: (int((v['resolution'] or '0k')[:-1] or 0), order.get(v['format'], 9)))
    return variants


def to_record(asset: dict, max_downloads: int) -> dict | None:
    kind = TYPES.get(asset.get('dataType'))
    slug = asset.get('assetId')
    if not kind or not isinstance(slug, str) or not re.fullmatch(r'[A-Za-z0-9._~-]{1,160}', slug):
        return None
    images = asset.get('previewImage') or {}
    variants = _variants(asset, kind)
    resolutions = sorted({v['resolution'] for v in variants if v['resolution']}, key=lambda r: int(r[:-1]))
    longest = int(resolutions[-1][:-1]) * 1024 if resolutions else None
    attributes = {}
    maps = [MAP_NAMES[m.lower()] for m in asset.get('maps') or [] if isinstance(m, str) and m.lower() in MAP_NAMES]
    if asset.get('dataType') == 'Material':  # the feed lists only some maps; every material zip has these
        maps += ['color', 'normal_gl', 'normal_dx', 'roughness', 'ao', 'displacement']
    if maps:
        attributes['maps'] = sorted(set(maps))
    if kind == 'texture' and asset.get('dimensionX') and asset.get('dimensionY'):
        attributes['real_size_m'] = [asset['dimensionX'] / 100, asset['dimensionY'] / 100]
    if asset.get('dataType') == 'Material':
        attributes['godot_material'] = True  # zips ship a ready Godot .tres material
    if asset.get('creationMethodName'):
        attributes['made_with'] = asset['creationMethodName']
    data_type = asset.get('dataType')
    tags = list(asset.get('tags') or [])
    if data_type in ('Decal', 'Atlas', 'Terrain'):
        tags.append(data_type.lower())
    category = asset.get('displayCategory')
    downloads = asset.get('downloadCount') or 0
    formats = sorted({v['format'] for v in variants if v['format'] in ('jpg', 'png', 'exr', 'hdr')})
    return {
        'source': 'ambientcg', 'source_id': slug, 'type': kind,
        'title': asset.get('customDisplayName') or asset.get('displayName') or slug,
        'description': asset.get('description') or '',
        'tags': [t for t in tags if isinstance(t, str) and not re.fullmatch(r'\d+', t) and t.lower() != slug.lower()],
        'categories': [category] if isinstance(category, str) and category else [],
        'style': 'realistic', 'license': 'CC0-1.0',
        'authors': [{'name': 'ambientCG (Lennart Demes)', 'url': 'https://ambientcg.com'}],
        'source_url': asset.get('shortLink') or f'https://ambientcg.com/a/{slug}',
        'thumbnail_url': _preview(images, 256), 'preview_url': _preview(images, 1024) or _preview(images, 512),
        'formats': formats, 'resolutions': resolutions, 'max_resolution': longest,
        'attributes': attributes,
        'downloads': variants,
        'popularity': math.log1p(downloads) / math.log1p(max_downloads) if max_downloads else 0,
        'published_at': _iso(asset.get('releaseDate')),
    }


def fetch_records(log=print, **_):
    offset, total, raw = 0, None, []
    while total is None or offset < total:
        page = net.get_json(FEED.format(limit=PAGE, offset=offset), timeout=90)
        found = page.get('foundAssets') or []
        if total is None:
            total = int(page.get('numberOfResults') or 0)
            log(f'ambientCG: {total} assets in the catalogue.')
        if not found:
            break
        raw += [a for a in found if isinstance(a, dict)]
        offset += len(found)
    # The whole feed is a few thousand entries: read it all, then scale popularity.
    top = max((a.get('downloadCount') or 0) for a in raw) if raw else 0
    for asset in raw:
        record = to_record(asset, top)
        if record:
            yield record


DEFAULT_VARIANT = {'texture': ['2k-jpg', '1k-jpg'], 'hdri': ['2k-exr', '1k-exr', '2k-hdr']}
