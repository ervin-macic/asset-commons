"""Poly Haven importer (https://polyhaven.com, all assets CC0).

The catalogue comes from one request to `api.polyhaven.com/assets`. File
listings are per asset (`/files/<id>`), so they are fetched only when someone
opens or downloads that asset, then stored. Poly Haven's API terms ask apps to
send an identifying User-Agent and to credit Poly Haven wherever its content
is shown; the UI's source credit and every asset's source label do that.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone

from .. import net

API = 'https://api.polyhaven.com'
TYPE_BY_CODE = {0: 'hdri', 1: 'texture', 2: 'model'}
MAP_NAMES = {
    'diffuse': 'color', 'diff': 'color', 'col': 'color', 'nor_gl': 'normal_gl', 'nor_dx': 'normal_dx',
    'rough': 'roughness', 'ao': 'ao', 'displacement': 'displacement', 'disp': 'displacement',
    'arm': 'arm', 'rough_ao': 'rough_ao', 'metal': 'metalness', 'bump': 'bump', 'spec': 'specular',
    'specular': 'specular', 'alpha': 'opacity', 'mask': 'mask', 'emission': 'emission', 'emissive': 'emission',
    'translucent': 'translucency', 'sheen': 'sheen', 'anisotropy': 'anisotropy',
}
DEFAULT_FORMATS = {'model': ['gltf', 'fbx', 'blend', 'usd'], 'texture': ['jpg', 'png', 'exr', 'gltf', 'blend'],
                   'hdri': ['hdr', 'exr']}
TEXTURE_MAPS = ['color', 'normal_gl', 'normal_dx', 'roughness', 'ao', 'displacement', 'arm']


def _iso(timestamp) -> str | None:
    try:
        return datetime.fromtimestamp(int(timestamp), timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    except (TypeError, ValueError, OSError):
        return None


def resolution_ladder(max_pixels: int | None) -> list[str]:
    if not max_pixels:
        return []
    top = max(1, round(max_pixels / 1024))
    steps = [1, 2, 4, 8, 16, 24, 32]
    ladder = [f'{s}k' for s in steps if s < top]
    return ladder + [f'{top}k']


def to_record(slug: str, data: dict, max_downloads: int) -> dict | None:
    kind = TYPE_BY_CODE.get(data.get('type'))
    if not kind or not re.fullmatch(r'[A-Za-z0-9._~-]{1,160}', slug):
        return None
    max_res = data.get('max_resolution') or []
    longest = max(max_res) if max_res else None
    dims = data.get('dimensions')
    attributes = {}
    dimensions = None
    if isinstance(dims, list) and len(dims) >= 2 and all(isinstance(v, (int, float)) for v in dims):
        metres = [round(v / 1000, 3) for v in dims]
        if kind == 'model' and len(metres) == 3:
            dimensions = metres
        elif kind == 'texture':
            attributes['real_size_m'] = metres[:2]
    if kind == 'texture':
        attributes['maps'] = TEXTURE_MAPS
    if kind == 'hdri':
        if data.get('evs_cap'):
            attributes['dynamic_range_ev'] = data['evs_cap']
        cats = set(data.get('categories') or [])
        attributes['lighting'] = ('studio' if 'studio' in cats else 'indoor' if 'indoor' in cats
                                  else 'night' if 'night' in cats else 'outdoor' if 'outdoor' in cats else None)
    extra = data.get('attributes') if isinstance(data.get('attributes'), dict) else {}
    tags = list(data.get('tags') or [])
    for values in extra.values():
        if isinstance(values, list):
            tags += [v for v in values if isinstance(v, str)]
    downloads = data.get('download_count') or 0
    thumb = data.get('thumbnail_url')
    preview = re.sub(r'width=\d+&height=\d+', 'width=720&height=720', thumb) if isinstance(thumb, str) else None
    return {
        'source': 'polyhaven', 'source_id': slug, 'type': kind, 'title': data.get('name') or slug,
        'description': data.get('description') or '', 'tags': tags,
        'categories': [c for c in data.get('categories') or [] if isinstance(c, str)],
        'style': 'realistic', 'license': 'CC0-1.0',
        'authors': [{'name': name, 'url': None} for name in (data.get('authors') or {})],
        'source_url': f'https://polyhaven.com/a/{slug}', 'thumbnail_url': thumb, 'preview_url': preview,
        'formats': DEFAULT_FORMATS[kind], 'resolutions': resolution_ladder(longest), 'max_resolution': longest,
        'polycount': data.get('polycount') if kind == 'model' else None, 'dimensions': dimensions,
        'attributes': {k: v for k, v in attributes.items() if v is not None},
        'popularity': math.log1p(downloads) / math.log1p(max_downloads) if max_downloads else 0,
        'published_at': _iso(data.get('date_published')),
    }


def fetch_records(log=print, **_):
    catalogue = net.get_json(f'{API}/assets?t=all', timeout=60)
    if not isinstance(catalogue, dict) or not catalogue:
        raise net.FetchError('Poly Haven returned an empty catalogue.')
    top = max((v.get('download_count') or 0) for v in catalogue.values() if isinstance(v, dict))
    log(f'Poly Haven: {len(catalogue)} assets in the catalogue.')
    for slug, data in catalogue.items():
        if isinstance(data, dict):
            record = to_record(slug, data, top)
            if record:
                yield record


def _file(entry: dict, path: str) -> dict | None:
    if isinstance(entry, dict) and isinstance(entry.get('url'), str):
        return {'path': path, 'url': entry['url'], 'size': entry.get('size'), 'md5': entry.get('md5')}
    return None


def _basename(url: str) -> str:
    return url.rsplit('/', 1)[-1].split('?', 1)[0]


def _res_key(res: str) -> int:
    match = re.match(r'(\d+)k', res)
    return int(match.group(1)) if match else 0


def variants_from_files(slug: str, kind: str, files: dict) -> tuple[list[dict], dict]:
    """Normalise a `/files/<id>` listing into downloadable variants."""
    variants: list[dict] = []
    maps_found: set[str] = set()
    if kind == 'hdri':
        for res, formats in sorted((files.get('hdri') or {}).items(), key=lambda kv: _res_key(kv[0])):
            for fmt in ('hdr', 'exr'):
                f = _file((formats or {}).get(fmt), '')
                if f:
                    f['path'] = _basename(f['url'])
                    variants.append({'id': f'{res}-{fmt}', 'label': f'{res.upper()} {fmt.upper()}',
                                     'resolution': res, 'format': fmt, 'files': [f]})
        tone = _file(files.get('tonemapped'), '')
        if tone:
            tone['path'] = _basename(tone['url'])
            variants.append({'id': 'tonemapped-jpg', 'label': 'Tonemapped JPG preview', 'resolution': None,
                             'format': 'jpg', 'files': [tone]})
        return variants, {}
    packages = {'model': ('gltf', 'fbx', 'blend', 'usd'), 'texture': ('gltf', 'blend', 'mtlx')}[kind]
    resolutions = set()
    for key, by_res in files.items():
        if isinstance(by_res, dict):
            resolutions |= {r for r in by_res if re.fullmatch(r'\d+k', r)}
    for res in sorted(resolutions, key=_res_key):
        if kind == 'texture':
            for fmt in ('jpg', 'png', 'exr'):
                maps = []
                for key, by_res in files.items():
                    name = MAP_NAMES.get(key.lower())
                    if not name or key in packages:
                        continue
                    f = _file(((by_res or {}).get(res) or {}).get(fmt), '')
                    if f:
                        f['path'] = _basename(f['url'])
                        maps.append(f)
                        maps_found.add(name)
                if maps:
                    variants.append({'id': f'{res}-{fmt}', 'label': f'{res.upper()} {fmt.upper()} maps',
                                     'resolution': res, 'format': fmt, 'files': maps})
        for fmt in packages:
            entry = ((files.get(fmt) or {}).get(res) or {}).get(fmt)
            main = _file(entry, '')
            if not main:
                continue
            main['path'] = _basename(main['url'])
            parts = [main]
            for include_path, include in (entry.get('include') or {}).items():
                f = _file(include, include_path)
                if f and not include_path.startswith(('/', '..')) and '..' not in include_path.split('/'):
                    parts.append(f)
            variants.append({'id': f'{res}-{fmt}', 'label': f'{res.upper()} {fmt.upper()}'
                             + (' + textures' if len(parts) > 1 else ''),
                             'resolution': res, 'format': fmt, 'files': parts})
    for variant in variants:
        variant['size'] = sum(f.get('size') or 0 for f in variant['files'])
    attributes = {'maps': sorted(maps_found)} if maps_found else {}
    return variants, attributes


def fetch_downloads(source_id: str, asset: dict) -> tuple[list[dict], dict]:
    files = net.get_json(f'{API}/files/{source_id}', timeout=12, max_bytes=4 * 1024 * 1024)
    if not isinstance(files, dict):
        raise net.FetchError('Poly Haven returned no file listing.')
    return variants_from_files(source_id, asset['type'], files)


DEFAULT_VARIANT = {'texture': ['2k-jpg', '1k-jpg'], 'model': ['2k-gltf', '1k-gltf'], 'hdri': ['2k-hdr', '1k-hdr']}
