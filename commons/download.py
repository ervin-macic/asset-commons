"""Pull one asset variant into a project folder, with its provenance.

Each download lands in `<dest_dir>/<folder>/` together with
`asset-commons.json` (machine-readable provenance: source, licence, authors,
files, checksums) and `ASSET-LICENSE.txt` (the human version). The credits
tool later rebuilds a project's CREDITS.md from those provenance files, so
attribution survives copying folders around.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

from . import VERSION, credits, net, remotezip
from .db import now
from .licenses import describe

PROVENANCE = 'asset-commons.json'
LICENSE_FILE = 'ASSET-LICENSE.txt'
ALLOWED_ROOTS = ('/data', '/tmp')
PROTECTED = ('/data/cli-auth', '/data/.secret-key', '/data/shared/memory', '/data/.git')


class DownloadError(Exception):
    pass


def resolve_dest(dest_dir: str) -> Path:
    if not isinstance(dest_dir, str) or not dest_dir.strip():
        raise DownloadError('dest_dir is required: the absolute folder to put the asset in, e.g. your '
                            'project’s assets/ folder.')
    path = Path(dest_dir.strip()).expanduser()
    if not path.is_absolute():
        raise DownloadError('dest_dir must be an absolute path.')
    real = os.path.realpath(path)
    if not any(real == root or real.startswith(root + '/') for root in ALLOWED_ROOTS):
        raise DownloadError('dest_dir must be inside /data (or /tmp for scratch work).')
    if any(real == p or real.startswith(p + '/') for p in PROTECTED):
        raise DownloadError('dest_dir points into a protected Möbius location.')
    return Path(real)


def choose_variant(asset: dict, defaults: list[str], *, variant=None, resolution=None, fmt=None) -> dict:
    variants = asset.get('downloads') or []
    if not variants:
        manual = (asset.get('attributes') or {}).get('manual_download')
        if manual:
            raise DownloadError(f'“{asset["title"]}” can’t be fetched automatically: {manual["note"]} '
                                f'Link: {manual["url"]}. Ask the owner to download it, or pick another asset.')
        raise DownloadError('This asset has no downloadable files listed.')
    if variant:
        found = next((v for v in variants if v['id'] == variant), None)
        if not found:
            raise DownloadError(f'Unknown variant “{variant}”. Available: '
                                + ', '.join(v['id'] for v in variants) + '.')
        return found
    pool = variants
    if resolution:
        want = str(resolution).lower().replace(' ', '')
        want = want if want.endswith('k') else f'{want}k'
        pool = [v for v in pool if (v.get('resolution') or '').lower() == want] or pool
    if fmt:
        pool = [v for v in pool if (v.get('format') or '').lower() == str(fmt).lower()] or pool
    if not resolution and not fmt:
        for preferred in defaults:
            found = next((v for v in pool if v['id'] == preferred), None)
            if found:
                return found
    return pool[0]


def _folder_name(asset: dict, base: Path, folder: str | None) -> Path:
    if folder:
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._ -]{0,100}', folder):
            raise DownloadError('folder must be a simple name (letters, digits, . _ - and spaces).')
        return base / folder
    candidate = base / ((asset.get('attributes') or {}).get('folder') or asset['source_id'])
    existing = candidate / PROVENANCE
    if existing.exists():
        try:
            if json.loads(existing.read_text()).get('asset_id') != asset['id']:
                candidate = base / f'{asset["source"]}-{asset["source_id"]}'
        except (OSError, ValueError):
            candidate = base / f'{asset["source"]}-{asset["source_id"]}'
    return candidate


def _safe_extract(archive: Path, target: Path, limit: int) -> list[Path]:
    written: list[Path] = []
    total = 0
    with zipfile.ZipFile(archive) as bundle:
        for info in bundle.infolist():
            name = info.filename.replace('\\', '/')
            if info.is_dir() or name.startswith('/') or '..' in name.split('/'):
                continue
            total += info.file_size
            if total > limit:
                raise DownloadError('The archive expands beyond the size limit; raise max_mb to allow it.')
            out = target / name
            out.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(info) as src, open(out, 'wb') as dst:
                shutil.copyfileobj(src, dst, 1024 * 256)
            written.append(out)
    return written


def provenance(asset: dict, variant: dict, files: list[dict]) -> dict:
    lic = describe(asset['license'])
    return {
        'asset_commons': VERSION, 'asset_id': asset['id'], 'title': asset['title'], 'type': asset['type'],
        'source': asset['source'], 'source_name': credits.SOURCE_NAMES.get(asset['source'], asset['source']),
        'source_url': asset.get('source_url'), 'authors': asset.get('authors') or [],
        'license': {'id': lic['id'], 'name': lic['name'], 'url': lic.get('url'),
                    'attribution_required': lic['attribution_required'], 'share_alike': lic['share_alike']},
        'credit': credits.credit_line(asset), 'variant': variant['id'], 'files': files,
        'downloaded_at': now(),
    }


def _license_text(asset: dict) -> str:
    lic = describe(asset['license'])
    lines = [asset['title'], '=' * len(asset['title']), '',
             f'Author: {credits.author_names(asset)}',
             f'Source: {credits.SOURCE_NAMES.get(asset["source"], asset["source"])} — {asset.get("source_url") or ""}',
             f'Licence: {lic["name"]} ({lic["short"]}) — {lic.get("url") or ""}', '',
             lic['summary'], '']
    if lic['attribution_required']:
        lines += ['Credit line to use:', credits.credit_line(asset), '']
    lines.append('Found through Asset Commons.')
    return '\n'.join(lines) + '\n'


MODEL_PREFERENCE = ('glb', 'gltf', 'fbx', 'obj')


def select_members(names: list[str], patterns: list[str], fmt: str | None = None) -> list[str]:
    """Pack files matching the requested names, plus what they need to work.

    A plain word matches file names that start with it ("tent" → tent.glb,
    tent-detailed.glb); a pattern with / or * is matched against the whole path.
    Without a format, one model format is kept per item (GLB first), and preview
    images are left out unless asked for. Textures folders beside a chosen
    model, .mtl files for .obj and the pack's licence file come along.
    """
    files = [n for n in names if not n.endswith('/')]
    matched: list[str] = []
    for raw in patterns or []:
        pattern = str(raw).strip().lower()
        if len(pattern.strip('*/ ')) < 3:
            raise DownloadError(f'pick patterns must be item names or paths of at least 3 characters (got “{raw}”).')
        for name in files:
            low = name.lower()
            base = low.rsplit('/', 1)[-1]
            if any(ch in pattern for ch in '*?[') or '/' in pattern:
                hit = fnmatch.fnmatch(low, pattern if pattern.startswith('*') else '*' + pattern)
            else:  # "campfire pit" matches campfire-pit.glb and campfire_pit.png
                words = [re.escape(w) for w in re.split(r'[\s_-]+', pattern) if w]
                hit = re.search(r'(^|[^a-z0-9])' + r'[\s_-]*'.join(words), base) is not None
            if hit and name not in matched:
                matched.append(name)
    wants_previews = any('preview' in str(p).lower() for p in patterns or [])
    if not wants_previews:
        matched = [n for n in matched if '/previews/' not in '/' + n.lower()]
    ext = lambda n: n.rsplit('.', 1)[-1].lower() if '.' in n else ''  # noqa: E731
    if fmt:
        allowed = {'gltf', 'glb'} if fmt.lower() in ('gltf', 'glb') else {fmt.lower()}
        matched = [n for n in matched if ext(n) in allowed]
    else:
        stems: dict[str, list[str]] = {}
        for name in matched:
            if ext(name) in MODEL_PREFERENCE:
                stems.setdefault(name.rsplit('/', 1)[-1].rsplit('.', 1)[0].lower(), []).append(name)
        for group in stems.values():
            best = min(group, key=lambda n: MODEL_PREFERENCE.index(ext(n)))
            matched = [n for n in matched if n not in group or n == best]
        # Material sidecars only travel with their own .obj.
        matched = [n for n in matched if not (ext(n) == 'mtl' and n[:-4] + '.obj' not in matched)]
    extra: list[str] = []
    for name in matched:
        folder = name.rsplit('/', 1)[0] + '/' if '/' in name else ''
        extra += [n for n in files if n.lower().startswith((folder + 'textures/').lower())]
        if ext(name) == 'obj':
            extra += [n for n in files if n.lower() == name.lower()[:-4] + '.mtl']
    extra += [n for n in files if '/' not in n and n.lower().startswith('license')]
    return list(dict.fromkeys(matched + extra)) if matched else []


def _run_pick(asset: dict, chosen: dict, target: Path, patterns: list[str], fmt: str | None,
              limit: int, overwrite: bool) -> dict:
    zips = [f for f in chosen.get('files') or [] if str(f.get('path', '')).lower().endswith('.zip')]
    if len(zips) != 1:
        if len(zips) > 1:
            raise DownloadError('This entry has several zips; pass variant with the one to pick from: '
                                + ', '.join(f['path'] for f in zips) + '.')
        raise DownloadError('pick works on packs that download as a zip; download the whole asset instead.')
    url = zips[0]['url']
    members = {m.name: m for m in remotezip.index(url)}
    wanted = select_members(list(members), patterns, fmt)
    if not wanted:
        names = (asset.get('attributes') or {}).get('contents') or []
        raise DownloadError(f'Nothing in “{asset["title"]}” matches {patterns}. It contains: '
                            + ', '.join(names[:40]) + ('…' if len(names) > 40 else '') + '.')
    total = sum(members[n].size for n in wanted)
    if total > limit:
        raise DownloadError(f'The picked files add up to {total / 1048576:.0f} MB, over the {limit // 1048576} MB limit.')
    target.mkdir(parents=True, exist_ok=True)
    written: list[dict] = []
    whole: Path | None = None
    try:
        for name in wanted:
            relative = Path(name)
            if relative.is_absolute() or '..' in relative.parts:
                continue
            out = target / relative
            if out.exists() and not overwrite and out.stat().st_size == members[name].size:
                written.append({'path': name, 'size': members[name].size, 'reused': True})
                continue
            out.parent.mkdir(parents=True, exist_ok=True)
            try:
                data = remotezip.extract(url, members[name], max_bytes=limit)
            except net.FetchError as exc:
                if 'partial' not in str(exc):
                    raise
                if whole is None:  # the server ignores ranges: fetch the archive once, then extract
                    whole = Path(tempfile.mkdtemp()) / 'pack.zip'
                    net.download(url, whole, max_bytes=limit * 8)
                with zipfile.ZipFile(whole) as bundle:
                    data = bundle.read(name)
            out.write_bytes(data)
            written.append({'path': name, 'size': len(data)})
    finally:
        if whole is not None:
            shutil.rmtree(whole.parent, ignore_errors=True)
    marker = target / PROVENANCE
    previous = []
    if marker.exists():
        try:
            old = json.loads(marker.read_text())
            if old.get('asset_id') == asset['id']:
                previous = [f for f in old.get('files') or [] if f['path'] not in {w['path'] for w in written}]
        except (OSError, ValueError):
            previous = []
    record = provenance(asset, chosen, previous + [{k: v for k, v in f.items() if k != 'reused'} for f in written])
    record['picked'] = list(patterns)
    marker.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    (target / LICENSE_FILE).write_text(_license_text(asset))
    return {'folder': str(target), 'variant': chosen, 'files': written,
            'reused': all(f.get('reused') for f in written), 'bytes': sum(f['size'] for f in written)}


def run(asset: dict, defaults: list[str], dest_dir: str, *, variant=None, resolution=None, fmt=None,
        folder=None, max_mb: float = 300, overwrite: bool = False, pick: list[str] | None = None) -> dict:
    """Download one variant (or picked files from a pack); returns what was written."""
    base = resolve_dest(dest_dir)
    chosen = choose_variant(asset, defaults, variant=variant, resolution=resolution,
                            fmt=None if pick else fmt)
    if pick and not variant and (len(chosen['files']) > 1 or chosen.get('archive') != 'zip'):
        # The default is not one zip (several files, or a single file): pick from the entry's zip when it has one.
        zipped = [v for v in asset.get('downloads') or [] if v.get('archive') == 'zip' and len(v['files']) == 1]
        if len(zipped) == 1:
            chosen = zipped[0]
    limit = int(max(1, min(float(max_mb or 300), 4096)) * 1024 * 1024)
    if pick:
        return _run_pick(asset, chosen, _folder_name(asset, base, folder), list(pick), fmt, limit, overwrite)
    declared = chosen.get('size') or sum(f.get('size') or 0 for f in chosen['files'])
    if declared and declared > limit:
        raise DownloadError(f'{chosen["label"]} is {declared / 1048576:.0f} MB, over the {limit // 1048576} MB '
                            'limit. Pick a smaller resolution or raise max_mb.')
    target = _folder_name(asset, base, folder)
    marker = target / PROVENANCE
    if marker.exists() and not overwrite:
        try:
            previous = json.loads(marker.read_text())
        except (OSError, ValueError):
            previous = {}
        if previous.get('asset_id') == asset['id'] and previous.get('variant') == chosen['id'] and all(
                (target / f['path']).exists() for f in previous.get('files') or []):
            return {'folder': str(target), 'variant': chosen, 'files': previous['files'], 'reused': True,
                    'bytes': sum(f.get('size') or 0 for f in previous['files'])}
    target.mkdir(parents=True, exist_ok=True)
    written: list[dict] = []
    used = 0
    for item in chosen['files']:
        relative = Path(item['path'])
        if relative.is_absolute() or '..' in relative.parts:
            continue
        out = target / relative
        if out.exists() and not overwrite and not marker.exists():
            raise DownloadError(f'{out} already exists; pass overwrite: true or choose another folder.')
        size = net.download(item['url'], out, max_bytes=limit - used, md5=item.get('md5'))
        used += size
        if chosen.get('archive') == 'zip' and out.suffix.lower() == '.zip':
            for path in _safe_extract(out, target, limit * 4):
                written.append({'path': str(path.relative_to(target)), 'size': path.stat().st_size})
            out.unlink()
        else:
            written.append({'path': str(relative), 'size': size, 'md5': item.get('md5')})
    record = provenance(asset, chosen, written)
    marker.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    (target / LICENSE_FILE).write_text(_license_text(asset))
    return {'folder': str(target), 'variant': chosen, 'files': written, 'reused': False,
            'bytes': sum(f['size'] for f in written)}


def scan(directory: str, limit: int = 2000) -> list[dict]:
    """Provenance records found under a folder (for CREDITS generation)."""
    root = resolve_dest(directory)
    found = []
    for path in root.rglob(PROVENANCE):
        if len(found) >= limit:
            break
        if any(part in ('node_modules', '.git', '.godot') for part in path.parts):
            continue
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and data.get('asset_id'):
            data['_folder'] = str(path.parent)
            found.append(data)
    return found
