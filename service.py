#!/usr/bin/env python3
"""Asset Commons service: the library behind the app and the agent tools.

Möbius runs this entry once per request with one JSON envelope on stdin and
reads one JSON response from stdout.

- The app UI calls `/api/apps/<id>/service/<path>` (overview, search, asset,
  credits, asset/status).
- Agent tools arrive as `POST /tools/<name>` (search, get, download, credits);
  agents see them as `asset_commons_<name>`. Each answer ends with an activity
  receipt line so the chat shows a card linking back into the app.
- The same UI routes answer owner-authenticated HTTP for scripts.

The tool lane runs concurrently with UI requests, so all writes go through
SQLite transactions (WAL, BEGIN IMMEDIATE).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from commons import db as database  # noqa: E402
from commons import library  # noqa: E402
from commons import resources  # noqa: E402
from commons.catalog import TYPES  # noqa: E402
from commons.download import DownloadError  # noqa: E402
from commons.net import FetchError  # noqa: E402
from commons.sources import freesound  # noqa: E402

LIVE_ERRORS = (freesound.NotConnected, freesound.Rejected, freesound.Throttled, FetchError)

MAX_TOOL_RESULTS = 50
RECEIPT = 'MOBIUS_APP_ACTIVITY_V1:'
# Bookkeeping kept with an asset that agents do not need to see.
INTERNAL_ATTRIBUTES = {'files', 'contents', 'contents_from', 'thumb_small', 'previews', 'preview_lq',
                       'audio_preview', 'default_variant', 'listed_at', 'details', 'slug', 'zip_url'}


class Problem(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def first(query, name):
    values = query.get(name) if isinstance(query, dict) else None
    if isinstance(values, list):
        return values[0] if values else None
    return values


def ui_params(query: dict) -> dict:
    params = {}
    for key in ('q', 'type', 'license', 'source', 'style', 'tags', 'category', 'format', 'min_resolution',
                'max_polycount', 'max_duration', 'sort', 'limit', 'offset'):
        value = first(query, key)
        if value not in (None, ''):
            params[key] = value
    return params


# --- App UI routes -----------------------------------------------------------------------

def ui_request(req: dict, conn) -> dict:
    path = (req.get('path') or '').strip('/')
    method = req.get('method')
    query = req.get('query') or {}
    body = req.get('body') if isinstance(req.get('body'), dict) else {}
    if path == 'overview' and method == 'GET':
        return library.overview(conn)
    if path == 'search' and method == 'GET':
        return library.search_assets(conn, ui_params(query))
    if path == 'asset' and method == 'GET':
        asset_id = first(query, 'id')
        try:
            # The UI lane must answer quickly: entries not read yet are queued (details_pending), not fetched.
            return library.get_asset(conn, asset_id, engine=first(query, 'engine'), fetch=False)
        except library.NotFound as exc:
            raise Problem(404, str(exc))
        except LIVE_ERRORS as exc:
            raise Problem(409 if isinstance(exc, freesound.NotConnected) else 502, str(exc))
    # Not "tools": Möbius reserves that first path segment for agent tool calls.
    if path == 'directory' and method == 'GET':
        return {'tools': resources.listing(conn, kind=first(query, 'kind'), makes=first(query, 'makes'),
                                           include_hidden=first(query, 'hidden') == '1'),
                'kinds': resources.KINDS}
    if path == 'directory/add' and method == 'POST':
        try:
            return library.add_resource(conn, body, {'kind': 'owner', 'label': 'owner'}, origin='owner')
        except resources.Invalid as exc:
            raise Problem(422, str(exc))
    if path == 'directory/status' and method == 'POST':
        try:
            return resources.set_status(conn, str(body.get('id') or ''), status=body.get('status'),
                                        verified=body.get('verified'))
        except resources.Invalid as exc:
            raise Problem(422, str(exc))
    if path == 'note' and method == 'POST':
        try:
            return library.add_note(conn, body.get('id'), body.get('text'), body.get('outcome') or 'tip',
                                    {'kind': 'owner', 'label': 'owner'})
        except (library.NotFound, resources.Invalid) as exc:
            raise Problem(422, str(exc))
    if path == 'note/remove' and method == 'POST':
        resources.remove_note(conn, body.get('id') or 0)
        return {'removed': True}
    if path == 'sources' and method == 'GET':
        return library.sources_status(conn)
    if path == 'sources/freesound/check' and method == 'POST':
        return library.sources_status(conn, check=True)
    if path == 'sources/freesound/forget' and method == 'POST':
        return library.forget_freesound(conn)
    if path == 'credits' and method == 'GET':
        ids = [part for part in (first(query, 'ids') or '').split(',') if part]
        return library.credits_for(conn, ids=ids)
    if path == 'asset/status' and method == 'POST':
        try:
            return library.set_status(conn, body.get('id'), body.get('status'), req.get('actor'),
                                      str(body.get('note') or ''))
        except library.NotFound as exc:
            raise Problem(404, str(exc))
        except ValueError as exc:
            raise Problem(422, str(exc))
    raise Problem(404, 'Not found.')


# --- Agent tools -------------------------------------------------------------------------------

def receipt(activity: str, status: str, label: str, detail: str | None = None, resources=None) -> str:
    payload = {'activity_id': activity, 'status': status, 'label': label}
    if detail:
        payload['detail'] = detail[:300]
    if resources:
        payload['resources'] = resources[:128]
    return RECEIPT + json.dumps(payload, ensure_ascii=False, separators=(',', ':'))


def resource(card: dict) -> dict:
    summary = ' · '.join(part for part in (
        TYPES.get(card['type'], {}).get('one', card['type']), card.get('license_short'),
        card.get('source_name'), card.get('specs')) if part)
    return {'label': card['title'][:120], 'summary': summary[:200], 'intent': f'asset:{card["id"]}'}


def human_size(size) -> str | None:
    if not size:
        return None
    if size >= 1048576:
        return f'{size / 1048576:.1f} MB'
    return f'{max(1, round(size / 1024))} KB'


def tool_card(card: dict) -> dict:
    data = {'id': card['id'], 'title': card['title'], 'type': card['type'], 'license': card['license_short'],
            'credit_required': card['attribution_required'], 'source': card['source_name'],
            'author': card['author'], 'specs': card['specs'], 'tags': card['tags'][:6]}
    if card.get('match') is not None and card['match'] < 1:
        data['match'] = card['match']
    if card.get('matched_items'):
        data['matched_items'] = card['matched_items']  # items inside a pack: use them with pick=[...]
    return data


def text(payload: dict, line: str) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(',', ':')) + '\n\n' + line


def tool_search(conn, args: dict) -> str:
    limit = max(1, min(int(args.get('limit') or 10), MAX_TOOL_RESULTS))
    params = {**args, 'limit': limit, 'facets': True}
    result = library.search_assets(conn, params)
    cards = result['results']
    payload = {
        'total': result['total'], 'results': [tool_card(c) for c in cards],
        'next_offset': result['next_offset'], 'interpreted': result['interpreted'],
        'by_type': result['facets'].get('type', {}),
    }
    if result.get('tools'):
        payload['tools'] = [{k: t[k] for k in ('id', 'name', 'kind', 'makes', 'pricing', 'access', 'summary',
                                               'output_terms')} for t in result['tools']]
    if result['notices']:
        payload['notices'] = result['notices']
    steps = []
    if cards:
        steps.append('Open a result with asset_commons_get for downloads and import notes, or call '
                     'asset_commons_download with its id and your project folder (pick=[...] fetches single '
                     'files from a pack).')
    if result.get('tools'):
        steps.append('If nothing fits, open a tool with asset_commons_get (tool:<id>) to see how to use it and '
                     'what its outputs may be used for.')
    steps.append('Learned something useful? Record it with asset_commons_note; found a good tool or source that '
                 'is not listed? Add it with asset_commons_add_resource.')
    payload['next_step'] = ' '.join(steps)
    query = (args.get('query') or '').strip()
    label = (f'Found {result["total"]} asset{"s" if result["total"] != 1 else ""}' if cards
             else 'No matching assets')
    detail = f'“{query[:80]}”' if query else 'Most popular assets'
    return text(payload, receipt('asset-search', 'succeeded' if cards else 'empty', label, detail,
                                 [resource(c) for c in cards]))


def tool_get(conn, args: dict) -> str:
    if str(args.get('id') or '').startswith('tool:'):
        entry = library.get_asset(conn, args['id'])
        return text(entry, receipt('asset-get', 'succeeded', entry['name'][:80],
                                   f'{entry["kind_label"]} · {entry["pricing"]}',
                                   [{'label': entry['name'], 'summary': entry['summary'][:200],
                                     'intent': f'tool:{entry["id"].removeprefix("tool:")}'}]))
    asset = library.get_asset(conn, args.get('id'), engine=args.get('engine'))
    wanted = args.get('variant') or asset.get('default_variant')
    variants = []
    for variant in asset['downloads']:
        entry = {'id': variant['id'], 'label': variant['label'],
                 'size': human_size(variant['size']) or 'not listed by the source', 'files': len(variant['files'])}
        if variant['id'] == wanted:
            entry['file_urls'] = [{'path': f['path'], 'url': f['url'], 'size': f['size']}
                                  for f in variant['files']]
        variants.append(entry)
    payload = {
        'id': asset['id'], 'title': asset['title'], 'type': asset['type'],
        'description': asset['description'][:1200], 'author': asset['author'],
        'source': asset['source_name'], 'page': asset['source_url'],
        'license': {k: asset['license_detail'][k] for k in ('id', 'short', 'url', 'attribution_required',
                                                            'share_alike', 'summary')},
        'credit': asset['credit'], 'specs': asset['specs'], 'tags': asset['tags'][:16],
        'categories': asset['categories'], 'dimensions_m': asset['dimensions_m'],
        'attributes': asset['attributes'], 'default_variant': asset.get('default_variant'),
        'variants': variants, 'import_notes': asset['import_notes'],
        'related': [{'id': r['id'], 'title': r['title']} for r in asset.get('related', [])[:5]],
    }
    payload['attributes'] = {k: v for k, v in (asset.get('attributes') or {}).items() if k not in INTERNAL_ATTRIBUTES}
    contents = (asset.get('attributes') or {}).get('contents') or []
    if contents:
        payload['contents'] = contents[:80] + (['…'] if len(contents) > 80 else [])
        payload['contents_hint'] = ('Pass pick=["name", …] to asset_commons_download to fetch only those files '
                                    '(plus their textures and the licence), e.g. pick=["' + contents[0] + '"].')
    if asset.get('source_notes'):
        payload['source_notes'] = asset['source_notes']
    if asset.get('field_notes'):
        payload['field_notes'] = asset['field_notes']
    if asset.get('details_pending'):
        payload['details_pending'] = ('Its page is queued to be read (the source asks for ten seconds between '
                                      'requests); call asset_commons_get again in a minute.')
    if asset.get('downloads_error'):
        payload['downloads_error'] = asset['downloads_error']
    return text(payload, receipt('asset-get', 'succeeded', asset['title'][:80],
                                 f'{asset["license_short"]} · {asset["source_name"]}', [resource(asset)]))


def tool_download(conn, args: dict, call: dict) -> str:
    actor = {'chat_id': call.get('chat_id'), 'provider': call.get('provider'), 'run_id': call.get('run_id')}
    result = library.download_asset(conn, args, actor)
    label = (f'Reused {result["asset"]["title"]}' if result['reused_existing_download']
             else f'Downloaded {result["asset"]["title"]}')
    detail = f'{result["variant"]} · {human_size(result["bytes"]) or "0 KB"} · {result["license"]} → {result["folder"]}'
    payload = {**result, 'asset': tool_card(result['asset'])}
    return text(payload, receipt('asset-download', 'succeeded', label[:80], detail, [resource(result['asset'])]))


def tool_credits(conn, args: dict) -> str:
    ids = library.as_list(args.get('ids'))
    result = library.credits_for(conn, ids=ids, directory=args.get('dir'),
                                 write=bool(args.get('write')), title=str(args.get('title') or 'Credits')[:80])
    label = f'Credits for {result["assets"]} asset{"s" if result["assets"] != 1 else ""}'
    detail = (f'{result["attribution_required"]} need attribution'
              + (f' · saved {result["written_to"]}' if result['written_to'] else ''))
    return text(result, receipt('asset-credits', 'succeeded' if result['assets'] else 'empty', label, detail))


def _agent(call: dict) -> dict:
    return {'kind': 'agent', 'label': 'agent', 'chat_id': call.get('chat_id'), 'provider': call.get('provider')}


def tool_add_resource(conn, args: dict, call: dict) -> str:
    result = library.add_resource(conn, args, _agent(call))
    entry = result['resource']
    label = ('Added ' if result['outcome'] == 'added' else 'Already listed: ') + entry['name']
    return text(result, receipt('asset-add-resource', 'succeeded', label[:80], entry['kind_label'],
                                [{'label': entry['name'], 'summary': entry['summary'][:200],
                                  'intent': f'tool:{entry["id"].removeprefix("tool:")}'}]))


def tool_note(conn, args: dict, call: dict) -> str:
    note = library.add_note(conn, args.get('id'), args.get('note'), args.get('outcome') or 'tip', _agent(call))
    return text({'saved': note, 'hint': 'Future agents see this note when they open the item.'},
                receipt('asset-note', 'succeeded', f'Note saved ({note["outcome"]})', note['text'][:120]))


TOOLS = {'search': tool_search, 'get': tool_get, 'download': tool_download, 'credits': tool_credits,
         'add_resource': tool_add_resource, 'note': tool_note}
ACTIVITY = {'search': 'asset-search', 'get': 'asset-get', 'download': 'asset-download', 'credits': 'asset-credits',
            'add_resource': 'asset-add-resource', 'note': 'asset-note'}
NEEDS_CALL = {'download', 'add_resource', 'note'}


def tool_request(req: dict, conn) -> dict:
    name = (req.get('path') or '').strip('/').split('/', 1)[-1]
    handler = TOOLS.get(name)
    if handler is None or req.get('method') != 'POST':
        return {'status': 404, 'body': {'detail': 'Unknown Asset Commons tool.'}}
    body = req.get('body') if isinstance(req.get('body'), dict) else {}
    args = body.get('arguments') if isinstance(body.get('arguments'), dict) else {}
    call = body.get('call') if isinstance(body.get('call'), dict) else {}
    try:
        output = handler(conn, args, call) if name in NEEDS_CALL else handler(conn, args)
        return {'status': 200, 'body': output}
    except (library.NotFound, DownloadError, ValueError, TypeError, resources.Invalid, *LIVE_ERRORS) as exc:
        message = str(exc)
        return {'status': 422, 'body': {'detail': message + '\n\n' + receipt(ACTIVITY[name], 'failed',
                                                                            'Asset Commons: ' + message[:70])}}


# --- Entry ---------------------------------------------------------------------------------------

def handle(req: dict) -> dict:
    if not isinstance(req, dict) or req.get('schema') != 1:
        return {'status': 400, 'body': {'error': 'Invalid service request.'}}
    if req.get('public'):
        return {'status': 404, 'body': {'error': 'Not found.'}}
    conn = database.connect()
    try:
        resources.ensure_seed(conn)
        if (req.get('path') or '').lstrip('/').startswith('tools/'):
            return tool_request(req, conn)
        scope = (req.get('actor') or {}).get('scope')
        if scope not in ('owner', 'app', 'agent'):
            return {'status': 403, 'body': {'error': 'Open Asset Commons from your signed-in Möbius.'}}
        try:
            return {'status': 200, 'body': ui_request(req, conn),
                    'headers': {'Cache-Control': 'private, no-store'}}
        except Problem as exc:
            return {'status': exc.status, 'body': {'error': exc.message}}
    finally:
        conn.close()


# Möbius may run the module setup above once and fork each request from it.
# Setup only imports modules: no files, sockets, threads or per-request values.
MOBIUS_PRELOAD = True

if __name__ == '__main__':
    try:
        response = handle(json.load(sys.stdin))
    except Exception as exc:  # keep the envelope valid; details go to the platform log
        print(f'{type(exc).__name__}: {exc}', file=sys.stderr)
        response = {'status': 500, 'body': {'error': 'Asset Commons hit an unexpected error. Please retry.'}}
    print(json.dumps(response, ensure_ascii=False, separators=(',', ':')))
