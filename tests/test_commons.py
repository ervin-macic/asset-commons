"""Offline tests for the Asset Commons catalogue, search, licences and tools.

Run from the project root:  python3 -m pytest -q tests
No network: source feeds come from small fixtures and downloads are faked.
"""
from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from commons import catalog, credits, db, download, library, licenses, net, search  # noqa: E402
from commons.sources import ambientcg, polyhaven  # noqa: E402

PH_FEED = {
    'mossy_rock': {'type': 1, 'name': 'Mossy Rock', 'categories': ['rock', 'natural'], 'tags': ['moss', 'stone'],
                   'authors': {'Rob Tuytel': 'All'}, 'max_resolution': [8192, 8192], 'dimensions': [3000, 3000],
                   'download_count': 5000, 'date_published': 1600000000, 'description': 'Rock with moss.',
                   'thumbnail_url': 'https://cdn.polyhaven.com/asset_img/thumbs/mossy_rock.png?width=256&height=256'},
    'wooden_chair': {'type': 2, 'name': 'Wooden Chair', 'categories': ['furniture'], 'tags': ['wood', 'seat'],
                     'authors': {'A': 'All', 'B': 'Model'}, 'max_resolution': [2048, 2048], 'polycount': 1500,
                     'dimensions': [500, 500, 900], 'download_count': 200, 'date_published': 1700000000,
                     'thumbnail_url': 'https://cdn.polyhaven.com/asset_img/thumbs/wooden_chair.png?width=256&height=256'},
    'sunset_field': {'type': 0, 'name': 'Sunset Field', 'categories': ['outdoor', 'sunrise-sunset'],
                     'tags': ['grass', 'dusk'], 'authors': {'C': 'All'}, 'max_resolution': [16384, 8192],
                     'download_count': 90000, 'date_published': 1650000000, 'evs_cap': 14},
}
ACG_ASSET = {
    'assetId': 'Bricks001', 'dataType': 'Material', 'displayName': 'Bricks 001', 'tags': ['bricks', 'red', '001'],
    'displayCategory': 'Bricks', 'shortLink': 'https://ambientcg.com/a/Bricks001', 'downloadCount': 300,
    'releaseDate': '2020-01-01 12:00:00', 'dimensionX': 100, 'dimensionY': 100, 'maps': ['Color'],
    'previewImage': {'256-WEBP': 'https://acg-media.struffelproductions.com/x/256-WEBP/Bricks001.webp'},
    'downloadFolders': {'default': {'downloadFiletypeCategories': {'zip': {'downloads': [
        {'fullDownloadPath': 'https://ambientcg.com/get?file=Bricks001_1K-JPG.zip', 'fileName': 'Bricks001_1K-JPG.zip',
         'size': 5_000_000, 'attribute': '1K-JPG'},
        {'fullDownloadPath': 'https://ambientcg.com/get?file=Bricks001_2K-JPG.zip', 'fileName': 'Bricks001_2K-JPG.zip',
         'size': 20_000_000, 'attribute': '2K-JPG'},
    ]}}}},
}


@pytest.fixture(autouse=True)
def _no_package_seed(tmp_path, monkeypatch):
    """Tests never import the real ready-made catalogue shipped in seed/."""
    from commons import seed as package_seed
    monkeypatch.setattr(package_seed, 'PACKAGE_DIR', tmp_path / 'no-package-seed')


@pytest.fixture()
def conn(tmp_path):
    connection = db.connect(tmp_path / 'test.sqlite3')
    with db.transaction(connection):
        for slug, data in PH_FEED.items():
            catalog.upsert(connection, polyhaven.to_record(slug, data, 90000))
        catalog.upsert(connection, ambientcg.to_record(ACG_ASSET, 300))
    yield connection
    connection.close()


def test_records_normalise_units_and_licence(conn):
    chair = catalog.get(conn, 'polyhaven:wooden_chair')
    assert chair['dimensions'] == [0.5, 0.5, 0.9]          # millimetres → metres
    assert chair['license'] == 'CC0-1.0' and chair['type'] == 'model'
    bricks = catalog.get(conn, 'ambientcg:Bricks001')
    assert bricks['attributes']['real_size_m'] == [1.0, 1.0]
    assert 'normal_gl' in bricks['attributes']['maps']
    assert [v['id'] for v in bricks['downloads']] == ['1k-jpg', '2k-jpg']


def test_upsert_keeps_owner_hidden_status(conn):
    library.set_status(conn, 'polyhaven:mossy_rock', 'hidden', {'scope': 'owner'})
    with db.transaction(conn):
        assert catalog.upsert(conn, polyhaven.to_record('mossy_rock', PH_FEED['mossy_rock'], 90000)) == 'updated'
    assert catalog.get(conn, 'polyhaven:mossy_rock')['status'] == 'hidden'


def test_natural_language_query_becomes_filters():
    parsed = search.parse_query('low-poly jungle trees, CC0, under 5k tris, 4k')
    assert parsed['terms'] == ['jungle', 'trees']
    assert parsed['filters']['style'] == ['low-poly'] and parsed['filters']['license'] == ['public-domain']
    assert parsed['numbers'] == {'max_polycount': 5000, 'min_resolution': 4000}
    assert search.parse_query('sunset sky hdri')['filters']['type'] == ['hdri']
    assert search.parse_query('footstep sound effects')['filters']['type'] == ['sound']


def test_search_ranks_full_concept_matches_first(conn):
    result = search.search(conn, 'mossy stone texture')
    assert result['results'][0]['id'] == 'polyhaven:mossy_rock'
    assert result['interpreted']['type'] == ['texture']


def test_explicit_filters_are_hard_and_inferred_style_relaxes(conn):
    assert search.search(conn, 'chair', type='hdri')['total'] == 0
    relaxed = search.search(conn, 'low-poly chair')
    assert relaxed['results'][0]['id'] == 'polyhaven:wooden_chair'
    assert any('low-poly' in notice for notice in relaxed['notices'])
    assert search.search(conn, 'chair', style='low-poly')['total'] == 0


def test_numeric_limits_and_facets(conn):
    assert search.search(conn, 'chair under 1000 polys')['notices']  # relaxed: the chair has 1,500
    assert search.search(conn, '', max_polycount=2000, type='model')['total'] == 1
    facets = search.search(conn, '', type='texture')['facets']
    assert facets['type'] == {'texture': 2, 'model': 1, 'hdri': 1}  # disjunctive: other tabs still counted


def test_licence_policy():
    assert licenses.resolve('cc by 4.0').id == 'CC-BY-4.0'
    assert licenses.refusal('CC-BY-NC-4.0').startswith('Non-commercial')
    assert licenses.refusal('CC BY-ND') and licenses.refusal('royalty free')
    assert licenses.refusal('CC0') is None
    assert licenses.filter_ids('cc0') == {'CC0-1.0', 'PDM-1.0'}


def test_credit_lines_and_credits_document():
    cc_by = {'id': 'x:1', 'title': 'Door Creak', 'source': 'freesound', 'license': 'CC-BY-4.0',
             'source_url': 'https://freesound.org/s/1', 'authors': [{'name': 'Ann'}]}
    cc0 = {'id': 'x:2', 'title': 'Rock', 'source': 'polyhaven', 'license': 'CC0-1.0', 'authors': [{'name': 'Bo'}]}
    line = credits.credit_line(cc_by)
    assert line.startswith('“Door Creak” by Ann, Freesound') and 'CC BY 4.0' in line
    text = credits.credits_markdown([cc_by, cc0, cc_by])
    assert text.count('Door Creak') == 1
    assert text.index('Attribution required') < text.index('Public domain')


def test_download_destination_is_confined(tmp_path):
    with pytest.raises(download.DownloadError):
        download.resolve_dest('relative/path')
    with pytest.raises(download.DownloadError):
        download.resolve_dest('/etc')
    with pytest.raises(download.DownloadError):
        download.resolve_dest('/data/cli-auth/x')
    assert download.resolve_dest(str(tmp_path)) == Path(str(tmp_path)).resolve()


def test_network_allow_list():
    assert net.check_url('https://dl.polyhaven.org/file/x.hdr')
    for url in ('http://dl.polyhaven.org/x', 'https://evil.example/x', 'https://127.0.0.1/x'):
        with pytest.raises(net.FetchError):
            net.check_url(url)


def _fake_zip():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as bundle:
        bundle.writestr('Bricks001_1K-JPG_Color.jpg', b'color')
        bundle.writestr('../escape.txt', b'nope')
    return buffer.getvalue()


def test_download_writes_provenance_and_reuses(conn, tmp_path, monkeypatch):
    def fake_download(url, path, *, max_bytes, md5=None, timeout=60):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_fake_zip())
        return path.stat().st_size
    monkeypatch.setattr(net, 'download', fake_download)
    dest = tmp_path / 'game' / 'assets'
    first = library.download_asset(conn, {'id': 'ambientcg:Bricks001', 'dest_dir': str(dest), 'resolution': '1k'})
    folder = dest / 'Bricks001'
    assert first['variant'] == '1k-jpg' and (folder / 'Bricks001_1K-JPG_Color.jpg').read_bytes() == b'color'
    assert not (tmp_path / 'game' / 'escape.txt').exists() and not (dest / 'escape.txt').exists()
    record = json.loads((folder / download.PROVENANCE).read_text())
    assert record['asset_id'] == 'ambientcg:Bricks001' and record['license']['id'] == 'CC0-1.0'
    again = library.download_asset(conn, {'id': 'ambientcg:Bricks001', 'dest_dir': str(dest), 'resolution': '1k'})
    assert again['reused_existing_download'] is True
    assert conn.execute('SELECT COUNT(*) FROM pulls').fetchone()[0] == 1
    made = library.credits_for(conn, directory=str(tmp_path / 'game'), write=True)
    assert made['assets'] == 1 and Path(made['written_to']).name == 'CREDITS.md'
    (tmp_path / 'game' / 'CREDITS.md').write_text('# My own credits\n')
    again = library.credits_for(conn, directory=str(tmp_path / 'game'), write=True)
    assert Path(again['written_to']).name == 'CREDITS.asset-commons.md'  # never clobbers a hand-written file


def test_oversized_variant_is_refused_before_fetching(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(net, 'download', lambda *a, **k: pytest.fail('must not fetch'))
    with pytest.raises(download.DownloadError, match='limit'):
        library.download_asset(conn, {'id': 'ambientcg:Bricks001', 'dest_dir': str(tmp_path), 'variant': '2k-jpg',
                                      'max_mb': 10})


def _service(tmp_path, monkeypatch, conn_path):
    import service
    monkeypatch.setattr(service.database, 'default_path', lambda: conn_path)
    return service


def test_service_ui_and_tool_routes(conn, tmp_path, monkeypatch):
    path = Path(conn.execute('PRAGMA database_list').fetchone()[2])
    service = _service(tmp_path, monkeypatch, path)
    owner = {'scope': 'owner'}
    found = service.handle({'schema': 1, 'method': 'GET', 'path': 'search', 'query': {'q': ['brick']},
                            'actor': owner})
    assert found['status'] == 200 and found['body']['results'][0]['id'] == 'ambientcg:Bricks001'
    refused = service.handle({'schema': 1, 'method': 'GET', 'path': 'search', 'query': {}, 'actor': {}})
    assert refused['status'] == 403
    public = service.handle({'schema': 1, 'method': 'GET', 'path': 'search', 'public': True})
    assert public['status'] == 404
    tool = service.handle({'schema': 1, 'method': 'POST', 'path': '/tools/search',
                           'body': {'arguments': {'query': 'wooden chair', 'limit': 3}, 'call': {'chat_id': 'c'}}})
    body, line = tool['body'].rsplit('\n\n', 1)
    assert json.loads(body)['results'][0]['id'] == 'polyhaven:wooden_chair'
    card = json.loads(line.removeprefix(service.RECEIPT))
    assert card['activity_id'] == 'asset-search' and card['resources'][0]['intent'] == 'asset:polyhaven:wooden_chair'
    missing = service.handle({'schema': 1, 'method': 'POST', 'path': '/tools/get',
                              'body': {'arguments': {'id': 'nope:1'}, 'call': {'chat_id': 'c'}}})
    assert missing['status'] == 422 and '"status":"failed"' in missing['body']['detail']


# --- Freesound (live source) -------------------------------------------------------------

from commons.sources import freesound  # noqa: E402

FS_SOUND = {
    'id': 123456, 'name': 'Footsteps on gravel.wav', 'tags': ['footsteps', 'gravel', 'walking'],
    'description': 'Walking on gravel.', 'username': 'alice',
    'license': 'http://creativecommons.org/publicdomain/zero/1.0/', 'duration': 4.2, 'samplerate': 44100,
    'channels': 2, 'type': 'wav', 'filesize': 740000, 'num_downloads': 1500, 'avg_rating': 4.5,
    'created': '2020-05-01T10:00:00.123',
    'previews': {'preview-hq-ogg': 'https://cdn.freesound.org/previews/123/123456_1-hq.ogg',
                 'preview-hq-mp3': 'https://cdn.freesound.org/previews/123/123456_1-hq.mp3',
                 'preview-lq-mp3': 'https://cdn.freesound.org/previews/123/123456_1-lq.mp3'},
    'images': {'waveform_m': 'https://cdn.freesound.org/displays/123/123456_1_wave_M.png'},
    'url': 'https://freesound.org/people/alice/sounds/123456/',
}


@pytest.fixture()
def live(monkeypatch):
    """Fake Freesound: records each API call and answers from FS_SOUND."""
    calls = []

    def fake_fetch(url, key):
        calls.append(url)
        assert key == 'test-key'
        if '/sounds/123456/' in url:
            return FS_SOUND
        return {'count': 4321, 'results': [FS_SOUND] if 'page_size=1&' not in url and 'fields=id&' not in url else []}
    monkeypatch.setattr(freesound, 'read_key', lambda: 'test-key')
    monkeypatch.setattr(freesound, '_fetch', fake_fetch)
    return calls


def test_freesound_sound_maps_to_a_cc0_asset():
    asset = freesound.to_asset(FS_SOUND)
    assert asset['id'] == 'freesound:123456' and asset['title'] == 'Footsteps on gravel'
    assert [v['id'] for v in asset['downloads']] == ['hq-ogg', 'hq-mp3', 'lq-mp3']
    assert asset['thumbnail_url'].endswith('_wave_M.png') and asset['license'] == 'CC0-1.0'
    assert freesound.to_asset({**FS_SOUND, 'license': 'http://creativecommons.org/licenses/by-nc/4.0/'}) is None


def test_sound_searches_go_live_and_are_cached(conn, live):
    first = library.search_assets(conn, {'q': 'footsteps on gravel sound', 'limit': 10})
    assert first['results'][0]['id'] == 'freesound:123456' and first['total'] == 4321
    assert first['facets']['type']['sound'] == 4321 and first['interpreted']['type'] == ['sound']
    assert 'license%3A%22Creative+Commons+0%22' in live[0]  # CC0 only, key sent as a header
    assert 'token=' not in live[0]
    library.search_assets(conn, {'q': 'footsteps on gravel sound', 'limit': 10})
    assert len(live) == 1  # second identical search came from the one-hour cache


def test_other_searches_count_sounds_and_fall_back_to_them(conn, live):
    textures = library.search_assets(conn, {'q': 'brick'})
    assert textures['results'][0]['id'] == 'ambientcg:Bricks001'
    assert textures['facets']['type']['sound'] == 4321  # tab count without fetching sound pages
    fallback = library.search_assets(conn, {'q': 'gravel footsteps'})
    assert fallback['results'][0]['id'] == 'freesound:123456'
    assert any('Freesound' in notice for notice in fallback['notices'])


def test_sound_search_without_a_key_explains_how_to_connect(conn, monkeypatch):
    def missing():
        raise freesound.NotConnected('Connect Freesound in Asset Commons (Sources) to search CC0 sounds.')
    monkeypatch.setattr(freesound, 'read_key', missing)
    result = library.search_assets(conn, {'q': 'rain', 'type': 'sound'})
    assert result['total'] == 0 and result['notices'] == [
        'Connect Freesound in Asset Commons (Sources) to search CC0 sounds.']
    assert library.sources_status(conn)['freesound']['state'] == 'not-connected'


def test_rejected_key_is_reported_not_raised(conn, monkeypatch):
    monkeypatch.setattr(freesound, 'read_key', lambda: 'bad')

    def refuse(url, key):
        raise net.FetchError('freesound.org answered 401', 401)
    monkeypatch.setattr(freesound, '_fetch', refuse)
    result = library.search_assets(conn, {'q': 'rain', 'type': 'sound'})
    assert any('rejected the saved API key' in notice for notice in result['notices'])
    assert library.sources_status(conn, check=True)['freesound']['state'] == 'rejected'


def test_live_sound_download_is_kept_as_provenance(conn, live, tmp_path, monkeypatch):
    fetched = []

    def fake_download(url, path, *, max_bytes, md5=None, timeout=60):
        fetched.append(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'OggS')
        return 4
    monkeypatch.setattr(net, 'download', fake_download)
    result = library.download_asset(conn, {'id': 'freesound:123456', 'dest_dir': str(tmp_path)})
    assert result['variant'] == 'hq-ogg' and fetched == [FS_SOUND['previews']['preview-hq-ogg']]
    assert Path(result['files'][0]).name == '123456-footsteps-on-gravel.ogg'
    stored = catalog.get(conn, 'freesound:123456')
    assert stored['origin'] == 'live' and stored['source_url'] == FS_SOUND['url']
    assert conn.execute('SELECT COUNT(*) FROM pulls').fetchone()[0] == 1
    credits_text = library.credits_for(conn, directory=str(tmp_path))['markdown']
    assert '“Footsteps on gravel” by alice, Freesound' in credits_text


def test_search_falls_back_to_the_older_text_endpoint(conn, monkeypatch):
    seen = []

    def old_api_only(url, key):
        seen.append(url.split('?')[0])
        if url.startswith(freesound.API + '/search/?'):
            raise net.FetchError('freesound.org answered 404', 404)
        return {'count': 1, 'results': [FS_SOUND]}
    monkeypatch.setattr(freesound, 'read_key', lambda: 'k')
    monkeypatch.setattr(freesound, '_fetch', old_api_only)
    found = freesound.search(conn, ['gravel'])
    assert found['assets'][0]['id'] == 'freesound:123456'
    assert seen == [freesound.API + '/search/', freesound.API + '/search/text/']


# --- Kenney and Quaternius packs ------------------------------------------------------------

from commons.sources import kenney, quaternius  # noqa: E402

KENNEY_LISTING = """
<div class='asset'><a href='https://kenney.nl/assets/mini-forest'><div class='cover'
 style='background-image:url("https://kenney.nl/media/pages/assets/mini-forest/a1/sample-400x.png")'></div></a>
<h2><a href='https://kenney.nl/assets/mini-forest'>Mini Forest</a></h2>
<span class='bold text-muted'><span><a href='https://kenney.nl/assets/category:3D'>3D</a></span>
<a href='https://kenney.nl/assets/series:Mini'>Mini</a></span></div>
<div class='asset'><a href='https://kenney.nl/assets/ui-pack'><div class='cover'
 style='background-image:url("https://kenney.nl/media/pages/assets/ui-pack/b2/sample-400x.png")'></div></a>
<h2><a href='https://kenney.nl/assets/ui-pack'>UI Pack</a></h2>
<span class='bold text-muted'><span><a href='https://kenney.nl/assets/category:2D'>2D</a></span></span></div>
<a href='https://kenney.nl/assets/page:2'>2</a>
"""
KENNEY_PACK = """<h1 class='x'>Mini Forest</h1><table><tbody>
<tr><td class='title text-muted'>Tags</td><td><a href='https://kenney.nl/assets/tag:forest' class='tag'>forest</a>
<a href='https://kenney.nl/assets/tag:archer' class='tag'>archer</a></td></tr>
<tr><td class='title text-muted'>Category</td><td class='bold'><a href='https://kenney.nl/assets/category:3D'>3D</a>
&#8226; <a href='https://kenney.nl/assets/series:Mini'>Mini</a></td></tr>
<tr><td class='title text-muted'>Features</td><td><span class='feature'><span style='p'>🎞️</span>Animation</span></td></tr>
<tr><td class='title text-muted'>Files</td><td>20×</td></tr>
<tr><td class='title text-muted'>License</td><td class='bold'><a href='https://creativecommons.org/publicdomain/zero/1.0/'
 target='_blank'>Creative Commons CC0</a></td></tr></tbody></table>
<a href='https://kenney.nl/media/pages/assets/mini-forest/c3/kenney_mini-forest_1.0.zip'>zip</a>
<td title='14/07/2026'><span class='type grey'>1.0</span><span class='description'>Released in 2026</span></td>
<a class='screenshot large' href='https://kenney.nl/media/pages/assets/mini-forest/d4/preview.png'></a>"""
QUATERNIUS_HOME = """
<div class="pack"><div class="hvr-sink"><a href="/packs/animatedwoman.html" ><img class="gallery-img"
 src="/assets/images/thumbnails/animatedwoman.jpg" /></a><div class="PackText">Animated Woman <!--TITLE -->
<div class="viewtag tags">Rigged</div></div><noscript>characterhumanwomananimatedrigged</noscript></div></div>"""
QUATERNIUS_PACK = """<title>Quaternius • Animated Woman</title>
<meta name="description" content="A <b>rigged</b> woman with 20 animations.">
<meta property="og:image" content="/assets/images/fullres/animatedwoman.jpg">
<div class="infoitem"><img src="/assets/svg/models.svg" class="iconBig"> Models<div class="text-right">3</div></div>
<div class="infoitem"><img src="/assets/svg/animated.svg" class="iconBig"> Animated<div class="text-right">
<img src="/assets/svg/check-solid.svg" class="icon"></div></div>
<div class="infoitem"><img src="/assets/svg/textured.svg" class="iconBig"> Textured<div class="text-right">
<img src="/assets/svg/xmark-solid.svg" class="icon"></div></div>
<div class="infoitem"><img src="/assets/svg/formats.svg" class="iconBig"> Formats
<div class="text-right tags">FBX</div><div class="text-right tags">glTF</div></div>
<div class="infoitem"><img src="/assets/svg/license.svg" class="iconBig"> License<div class="text-right">
<a href="https://creativecommons.org/publicdomain/zero/1.0/" target="_blank" >CC0</a></div></div>
<button onclick="window.open('https://quaternius.itch.io/animated-woman','_blank');">Download on Itch.io</button>"""


def test_kenney_pages_become_pack_records():
    cards, last = kenney.parse_listing(KENNEY_LISTING)
    assert last == 2 and [c['slug'] for c in cards] == ['mini-forest', 'ui-pack']
    pack = kenney.parse_pack(KENNEY_PACK, 'mini-forest')
    assert pack['features'] == ['Animation'] and pack['files'] == 20 and pack['version'] == '1.0'
    record = kenney.to_record(cards[0], pack)
    assert record['type'] == 'model' and record['extra_types'] == ['animation'] and record['style'] == 'low-poly'
    assert record['downloads'][0]['files'][0]['path'] == 'kenney_mini-forest_1.0.zip'
    assert record['published_at'] == '2026-07-14T00:00:00Z'
    ui = kenney.to_record(cards[1], {**kenney.parse_pack(KENNEY_PACK, 'ui-pack'), 'title': 'UI Pack',
                                     'category': '2D', 'features': []})
    assert ui['type'] == 'ui'
    assert kenney.to_record(cards[0], {**pack, 'license_text': 'Royalty free', 'license_url': None}) is None


def test_kenney_refetches_only_stale_pack_pages():
    pages = []

    def get(url):
        pages.append(url)
        if url.endswith('/assets'):
            return KENNEY_LISTING.replace("page:2'", "page:1'")
        return KENNEY_PACK.replace('mini-forest', url.rsplit('/', 1)[-1])
    fresh = kenney.to_record(kenney.parse_listing(KENNEY_LISTING)[0][0],
                             {**kenney.parse_pack(KENNEY_PACK, 'mini-forest'), 'fetched_at': db.now()})
    records = list(kenney.fetch_records(lambda *_: None, known={'mini-forest': fresh}, get=get, pause=0))
    assert [r['source_id'] for r in records] == ['mini-forest', 'ui-pack']
    assert not any(url.endswith('/mini-forest') for url in pages)  # carried forward, not refetched


def test_quaternius_packs_have_previews_but_manual_download(conn, tmp_path):
    cards = quaternius.parse_home(QUATERNIUS_HOME)
    pack = quaternius.parse_pack(QUATERNIUS_PACK, 'animatedwoman')
    assert pack['animated'] and not pack['textured'] and pack['formats'] == ['fbx', 'gltf'] and pack['models'] == 3
    record = quaternius.to_record(cards[0], pack, set())
    assert record['type'] == 'model' and record['extra_types'] == ['animation']
    assert 'Keywords: character, human, woman, animated, rigged.' in record['description']
    with db.transaction(conn):
        catalog.upsert(conn, record)
    with pytest.raises(download.DownloadError, match='quaternius.itch.io/animated-woman'):
        library.download_asset(conn, {'id': 'quaternius:animatedwoman', 'dest_dir': str(tmp_path)})


def test_multi_role_assets_and_style_tags_in_search(conn):
    card = kenney.parse_listing(KENNEY_LISTING)[0][0]
    with db.transaction(conn):
        catalog.upsert(conn, kenney.to_record(card, kenney.parse_pack(KENNEY_PACK, 'mini-forest')))
        catalog.upsert(conn, quaternius.to_record(quaternius.parse_home(QUATERNIUS_HOME)[0],
                                                  {**quaternius.parse_pack(QUATERNIUS_PACK, 'animatedwoman'),
                                                   'title': 'Stylized Animated Woman'}, set()))
    animations = search.search(conn, '', type='animation')
    assert {r['id'] for r in animations['results']} == {'kenney:mini-forest', 'quaternius:animatedwoman'}
    assert search.search(conn, 'forest', type='model')['results'][0]['id'] == 'kenney:mini-forest'
    facets = search.search(conn, '')['facets']['type']
    assert facets['animation'] == 2 and facets['model'] == 3  # counted under each role
    low_poly = search.search(conn, '', style='low-poly', type='model')  # stylized pack tagged low-poly
    assert 'quaternius:animatedwoman' in {r['id'] for r in low_poly['results']}
    assert search.search(conn, 'animated character')['interpreted']['type'] == ['animation']


def test_existing_libraries_gain_the_extra_types_column(tmp_path):
    old = db.connect(tmp_path / 'old.sqlite3')  # then turn it back into a version-2 library
    old.execute('ALTER TABLE assets DROP COLUMN extra_types')
    old.execute('PRAGMA user_version=2')
    old.close()
    upgraded = db.connect(tmp_path / 'old.sqlite3')
    columns = {row[1] for row in upgraded.execute('PRAGMA table_info(assets)')}
    assert 'extra_types' in columns and upgraded.execute('PRAGMA user_version').fetchone()[0] == db.SCHEMA_VERSION


def test_quaternius_download_links_follow_each_page_style():
    drive_page = QUATERNIUS_PACK.replace("window.open('https://quaternius.itch.io/animated-woman','_blank');", "") \
        + '<a href="https://drive.google.com/drive/folders/AbC_123-x?usp=sharing">Download</a>'
    named_page = QUATERNIUS_PACK.replace("window.open('https://quaternius.itch.io/animated-woman','_blank');", "") \
        + 'Itch.attachBuyButton(button, { user: "quaternius", game: "animated-woman-pack" })'
    card = quaternius.parse_home(QUATERNIUS_HOME)[0]
    links = {name: quaternius.to_record(card, quaternius.parse_pack(page, 'animatedwoman'), set())
             ['attributes']['manual_download'] for name, page in
             (('itch', QUATERNIUS_PACK), ('drive', drive_page), ('named', named_page))}
    assert links['itch']['url'] == 'https://quaternius.itch.io/animated-woman'
    assert links['drive']['url'] == 'https://drive.google.com/drive/folders/AbC_123-x' and 'Drive' in links['drive']['label']
    assert links['named']['url'] == 'https://quaternius.itch.io/animated-woman-pack'


def test_sound_tab_count_stays_live_on_other_tabs(conn, live):
    textures = library.search_assets(conn, {'q': 'brick', 'type': 'texture'})
    assert textures['facets']['type']['sound'] == 4321          # tab count still includes Freesound
    assert 'freesound' not in textures['facets'].get('source', {})  # other facets describe textures only
    assert textures['results'][0]['type'] == 'texture'


# --- Tools directory, pack contents and search behaviour -----------------------------------

from commons import resources  # noqa: E402


def test_directory_answers_how_to_make_things(conn):
    assert resources.ensure_seed(conn) >= 15 and resources.ensure_seed(conn) == 0  # loads once per file version
    rig = [t['id'] for t in library.search_assets(conn, {'q': 'rig my character'})['tools']]
    assert 'tool:mixamo' in rig and 'tool:meshy' in rig
    made = library.search_assets(conn, {'q': 'generate a wooden chair'})
    assert made['tools'] and all(t['kind'] in ('generator', 'tool', 'library') for t in made['tools'])
    assert any('Tools that can make this' in n for n in made['notices'])
    meshy = library.get_asset(conn, 'tool:meshy')
    assert 'CC BY 4.0' in meshy['output_terms'] and meshy['verified']
    few = library.search_assets(conn, {'q': 'mossy stone texture'})  # one match: texture makers are offered
    assert few['tools'] and not any(t['matched_words'] for t in few['tools'])
    with db.transaction(conn):
        for n in range(3):
            catalog.upsert(conn, {'source': 'ambientcg', 'source_id': f'MossyStone{n}', 'type': 'texture',
                                  'title': f'Mossy Stone {n}', 'license': 'CC0-1.0', 'tags': ['moss', 'stone']})
    assert library.search_assets(conn, {'q': 'mossy stone texture'})['tools'] == []  # good matches: no noise


def test_agents_add_links_and_field_notes(conn):
    resources.ensure_seed(conn)
    added = library.add_resource(conn, {'name': 'Asset Forge', 'url': 'https://kenney.nl/tools/asset-forge',
                                        'kind': 'tool', 'makes': ['model'], 'pricing': 'paid',
                                        'description': 'Build low-poly models from blocks.'}, {'label': 'agent'})
    assert added['outcome'] == 'added' and not added['resource']['verified']
    again = library.add_resource(conn, {'name': 'Forge', 'url': 'https://www.kenney.nl/tools/asset-forge/',
                                        'description': 'The same link written differently.'})
    assert again['outcome'] == 'already listed'
    with pytest.raises(resources.Invalid):
        library.add_resource(conn, {'name': 'x', 'url': 'ftp://nope', 'description': 'not a web link at all'})
    library.add_note(conn, 'tool:meshy', 'Rigging failed on a four-legged dog model.', 'problem', {'label': 'agent'})
    library.add_note(conn, 'polyhaven:wooden_chair', 'Scale is real-world; no change needed in Godot.', 'tip')
    assert library.get_asset(conn, 'tool:meshy')['field_notes'][0]['outcome'] == 'problem'
    assert library.get_asset(conn, 'polyhaven:wooden_chair')['field_notes'][0]['text'].startswith('Scale')
    with pytest.raises(resources.Invalid):
        library.add_note(conn, 'tool:meshy', 'ok', 'tip')
    hidden = resources.set_status(conn, 'tool:asset-forge', status='hidden')
    assert hidden['status'] == 'hidden' and 'tool:asset-forge' not in [t['id'] for t in resources.listing(conn)]


def test_pack_contents_are_searchable_and_pickable(conn):
    card = kenney.parse_listing(KENNEY_LISTING)[0][0]
    record = kenney.to_record(card, kenney.parse_pack(KENNEY_PACK, 'mini-forest'))
    record['attributes'].update(kenney.read_contents.__globals__['item_names'] and
                                {'contents': kenney.item_names(['Models/GLB format/campfire-pit.glb',
                                                                'Models/GLB format/tent.glb', 'License.txt'])})
    with db.transaction(conn):
        catalog.upsert(conn, record)
    found = search.search(conn, 'campfire')
    assert found['results'][0]['id'] == 'kenney:mini-forest'
    assert found['results'][0]['matched_items'] == ['campfire pit']
    names = ['License.txt', 'Models/GLB format/tent.glb', 'Models/GLB format/Textures/colormap.png',
             'Models/OBJ format/tent.obj', 'Models/OBJ format/tent.mtl', 'Previews/tent.png']
    assert download.select_members(names, ['tent']) == ['Models/GLB format/tent.glb',
                                                         'Models/GLB format/Textures/colormap.png', 'License.txt']
    assert download.select_members(names, ['tent'], 'obj')[:2] == ['Models/OBJ format/tent.obj',
                                                                   'Models/OBJ format/tent.mtl']
    assert download.select_members(names, ['dragon']) == []


def test_short_words_match_exactly_and_photos_rank_below_objects(conn):
    with db.transaction(conn):
        catalog.upsert(conn, {'source': 'polyhaven', 'source_id': 'wooden_bowl', 'type': 'model',
                              'title': 'Wooden Bowl', 'license': 'CC0-1.0', 'tags': ['bowl', 'kitchen']})
        catalog.upsert(conn, {'source': 'polyhaven', 'source_id': 'grass_tuft', 'type': 'model',
                              'title': 'Tuft', 'license': 'CC0-1.0', 'tags': ['grass']})
    assert 'polyhaven:wooden_bowl' not in [r['id'] for r in search.search(conn, 'bow')['results']]
    order = [r['id'] for r in search.search(conn, 'grass')['results']]
    assert order.index('polyhaven:grass_tuft') < order.index('polyhaven:sunset_field')  # HDRI tagged grass
    assert search.search(conn, 'font')['interpreted']['concepts'] == ['font']


def test_service_exposes_directory_tools(conn, tmp_path, monkeypatch):
    path = Path(conn.execute('PRAGMA database_list').fetchone()[2])
    service = _service(tmp_path, monkeypatch, path)
    call = {'chat_id': 'c', 'provider': 'claude'}
    added = service.handle({'schema': 1, 'method': 'POST', 'path': '/tools/add_resource', 'body': {
        'arguments': {'name': 'Example Gen', 'url': 'https://example-gen.test/app', 'kind': 'generator',
                      'makes': ['model'], 'description': 'Makes example models from text prompts.'}, 'call': call}})
    assert added['status'] == 200 and '"outcome":"added"' in added['body']
    noted = service.handle({'schema': 1, 'method': 'POST', 'path': '/tools/note', 'body': {
        'arguments': {'id': 'tool:example-gen', 'note': 'Outputs arrive with flipped normals.', 'outcome': 'problem'},
        'call': call}})
    assert noted['status'] == 200 and 'asset-note' in noted['body']
    # The platform reserves the first path segment "tools" for agent calls, so the UI uses "directory".
    listed = service.handle({'schema': 1, 'method': 'GET', 'path': 'directory', 'query': {}, 'actor': {'scope': 'owner'}})
    assert any(t['id'] == 'tool:example-gen' for t in listed['body']['tools'])
    import re as _re
    ui_routes = _re.findall(r"call\('([^']+)'", (ROOT / 'lib' / 'api.js').read_text())
    assert ui_routes and not any(route.split('/')[0] == 'tools' for route in ui_routes)


def test_pick_accepts_item_names_and_any_list_form():
    names = ['License.txt', 'Models/GLB format/campfire-pit.glb', 'Models/GLB format/campfire-stand.glb',
             'Models/GLB format/chest.glb', 'Models/GLB format/Textures/colormap.png']
    assert download.select_members(names, ['campfire pit']) == ['Models/GLB format/campfire-pit.glb',
                                                                'Models/GLB format/Textures/colormap.png',
                                                                'License.txt']
    with pytest.raises(download.DownloadError, match='at least 3'):
        download.select_members(names, ['c'])
    assert library.as_list('["campfire pit", "chest"]') == ['campfire pit', 'chest']  # JSON text from a runtime
    assert library.as_list('campfire pit, chest') == ['campfire pit', 'chest']
    assert library.as_list(['tent']) == ['tent'] and library.as_list(None) == []


# --- OpenGameArt ---------------------------------------------------------------------------------

import urllib.parse  # noqa: E402

from commons import pace  # noqa: E402
from commons.sources import opengameart as oga  # noqa: E402

OGA_DIR = ROOT / 'tests' / 'fixtures' / 'opengameart'
EMPTY_LISTING = '<div class="view-header">Displaying 0 - 0 of 0</div>'


def _oga_page(name: str) -> str:
    return (OGA_DIR / name).read_text()


def _oga_site(missing=()):
    """A fake opengameart.org made of saved pages; returns (get, requested urls)."""
    music, art2d, kenney_list = _oga_page('listing_music.html'), _oga_page('listing_2d.html'), _oga_page('listing_kenney.html')
    item_music, item_kenney = _oga_page('item_music.html'), _oga_page('item_2d_kenney.html')
    requested = []

    def get(url):
        requested.append(url)
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        if '/art-search-advanced' in url:
            if query.get('name') == ['Kenney']:
                return kenney_list
            if query.get('page', ['0']) != ['0']:
                return EMPTY_LISTING
            return {'12': music, '9': art2d}.get(query.get('field_art_type_tid[]', [''])[0], EMPTY_LISTING)
        slug = url.rsplit('/content/', 1)[-1]
        if slug in missing:
            raise net.FetchError(f'opengameart.org answered 404 for /content/{slug}', 404)
        if slug == 'skyboxes-space':
            return item_kenney
        if slug in ('cold-0', 'october-jazz', 'old-amusement-park', 'promise'):
            return item_music.replace('Old Amusement Park', slug.replace('-', ' ').title())
        # Other 2D entries: the skybox page, uploaded by someone other than Kenney.
        return (item_kenney.replace('/users/kenney">Kenney', '/users/artist">Artist')
                .replace('Skyboxes Space', slug.replace('-', ' ').title()))
    return get, requested


def test_opengameart_pages_parse():
    cards, total = oga.parse_listing(_oga_page('listing_music.html'))
    assert total == 4124 and [c['slug'] for c in cards] == ['cold-0', 'october-jazz', 'old-amusement-park', 'promise']
    assert cards[0]['audio']['mp3'].endswith('/cold_0.mp3') and cards[0]['image'].endswith('cold_0.mp3.png')
    music = oga.parse_item(_oga_page('item_music.html'))
    assert music['licenses'] == ['CC0'] and music['author_user'] == 'hothxcc' and music['art_types'] == ['Music']
    assert music['files'] == [{'name': 'old_amusement_park.wav', 'url': 'https://opengameart.org/sites/default/files/'
                               'old_amusement_park.wav', 'mime': 'audio/x-wav', 'size': 31750750, 'downloads': 6}]
    three = oga.parse_item(_oga_page('item_3d.html'))
    assert len(three['files']) == 4 and three['favorites'] == 7 and three['published_at'] == '2026-10-04T13:09:00Z'
    assert 'Light Attacks' in three['description']
    assert 'not mandatory' in oga.parse_item(_oga_page('item_2d_kenney.html'))['notice']


def test_opengameart_entries_become_records():
    record, why = oga.build('old-amusement-park', oga.parse_item(_oga_page('item_music.html')))
    assert why is None and record['type'] == 'music' and record['duration'] == 119.0
    assert record['attributes']['default_variant'] == 'preview-ogg'  # the WAV original is 32 MB
    assert {'wav', 'ogg', 'mp3'} <= set(record['formats']) and record['license'] == 'CC0-1.0'
    assert record['authors'] == [{'name': 'hothxcc', 'url': 'https://opengameart.org/users/hothxcc'}]
    anims, _ = oga.build('humanoid-soulslike-animations', oga.parse_item(_oga_page('item_3d.html')))
    assert anims['type'] == 'animation' and anims['style'] == 'low-poly'
    assert [v['id'] for v in anims['downloads']][:2] == ['all', 'playerfistweaponanimations.blend']
    assert anims['downloads'][0]['size'] == 1720512 + 2413282 + 6730770 + 3216297
    skipped, why = oga.build('skyboxes-space', oga.parse_item(_oga_page('item_2d_kenney.html')))
    assert skipped is None and 'kenney.nl' in why
    not_cc0 = {**oga.parse_item(_oga_page('item_music.html')), 'licenses': ['CC-BY 3.0']}
    assert oga.build('x', not_cc0)[0] is None
    odd = oga.source_id_for('crosshair-pack-200%C3%97')
    assert catalog._ID_PART.fullmatch(odd) and odd != oga.source_id_for('crosshair-pack-200')


def test_pace_spaces_requests(tmp_path, monkeypatch):
    monkeypatch.setenv('APP_STORAGE_DIR', str(tmp_path))
    waits = []
    clock = lambda: 1000.0  # noqa: E731
    for _ in range(3):
        pace.wait('example.org', 10, sleep=waits.append, clock=clock)
    assert waits == [10, 20]  # the first request goes at once
    with pytest.raises(pace.Busy):
        pace.wait('example.org', 10, max_wait=5, sleep=waits.append, clock=clock)


def test_opengameart_crawl_lists_reads_and_skips_kenney(conn, tmp_path, monkeypatch):
    monkeypatch.setenv('APP_STORAGE_DIR', str(tmp_path))
    get, requested = _oga_site(missing={'promise'})
    result = oga.run(conn, lambda *a: None, get=get, sleep=lambda s: None)
    assert conn.execute("SELECT COUNT(*) FROM assets WHERE id='opengameart:skyboxes-space'").fetchone()[0] == 0
    music = catalog.get(conn, 'opengameart:cold-0')
    assert music['type'] == 'music' and music['attributes']['details'] == 'complete' and music['downloads']
    assert catalog.get(conn, 'opengameart:promise')['status'] == 'hidden'  # 404: removed from the site
    sprite = catalog.get(conn, 'opengameart:more-blocks')
    assert sprite['type'] == 'sprite' and 'hdri' in sprite['extra_types']  # tagged skybox
    assert conn.execute('SELECT COUNT(*) FROM crawl_queue').fetchone()[0] == 0
    assert result['published'] == 6 and result['counts']['skipped (Kenney)'] == 1
    status = conn.execute("SELECT * FROM sources WHERE id='opengameart'").fetchone()
    assert status['last_status'] == 'ok' and status['asset_count'] == 6
    assert sum('/content/' in url for url in requested) == 7  # each entry page once, Kenney's never
    assert search.search(conn, 'cold', type='music')['results'][0]['id'] == 'opengameart:cold-0'
    # The next run is a short new-entries pass that finds nothing new and reads nothing.
    requested.clear()
    with db.transaction(conn):
        conn.execute("UPDATE meta SET value=json_set(value, '$.new_at', '2000-01-01T00:00:00Z') "
                     "WHERE key='opengameart_state'")
    oga.run(conn, lambda *a: None, get=get, sleep=lambda s: None)
    assert requested and not any('/content/' in url for url in requested)


def test_opengameart_full_pass_withdraws_and_restores(conn, tmp_path, monkeypatch):
    monkeypatch.setenv('APP_STORAGE_DIR', str(tmp_path))
    get, _ = _oga_site()
    oga.run(conn, lambda *a: None, get=get, sleep=lambda s: None)
    with db.transaction(conn):  # an entry the site no longer lists, and one it lists again
        catalog.upsert(conn, oga.listing_record({'slug': 'gone-entry', 'title': 'Gone'}, 'Music'))
        conn.execute("UPDATE assets SET status='hidden' WHERE id='opengameart:cold-0'")
        oga._event(conn, 'opengameart:cold-0', oga.WITHDRAWN, 'test')
    oga.run(conn, lambda *a: None, get=get, sleep=lambda s: None, refresh=True)
    assert catalog.get(conn, 'opengameart:gone-entry')['status'] == 'hidden'
    assert catalog.get(conn, 'opengameart:cold-0')['status'] == 'published'


def test_ui_queues_entry_pages_and_agents_read_them_now(conn, tmp_path, monkeypatch):
    monkeypatch.setenv('APP_STORAGE_DIR', str(tmp_path))
    cards, _ = oga.parse_listing(_oga_page('listing_music.html'))
    with db.transaction(conn):
        catalog.upsert(conn, oga.listing_record(cards[2], 'Music'))
    kicks = []
    monkeypatch.setattr(library, 'kick_sync', lambda db_, **k: kicks.append(1) or True)
    shown = library.get_asset(conn, 'opengameart:old-amusement-park', fetch=False)
    assert shown['details_pending'] and shown['downloads'] == [] and kicks
    assert conn.execute('SELECT priority FROM crawl_queue').fetchone()[0] == 1
    get, _ = _oga_site()
    monkeypatch.setattr(oga, '_get', get)
    monkeypatch.setattr(oga.pace, 'wait', lambda *a, **k: 0)
    opened = library.get_asset(conn, 'opengameart:old-amusement-park')
    assert not opened.get('details_pending') and opened['default_variant'] == 'preview-ogg'
    assert any('declared by the uploader' in note for note in opened['source_notes'])
    assert conn.execute('SELECT COUNT(*) FROM crawl_queue').fetchone()[0] == 0


def test_music_words_and_chiptune():
    parsed = search.parse_query('calm loopable music')
    assert parsed['filters']['type'] == ['music'] and parsed['terms'] == ['calm', 'loopable']
    chip = search.parse_query('8-bit battle music')
    assert 'style' not in chip['filters'] and chip['terms'] == ['chiptune', 'battle']
    assert search.parse_query('8-bit platformer sprites')['filters']['style'] == ['pixel']
    assert kenney.classify('Audio', 'Music Jingles', [], None, [])[0] == 'music'


def test_pick_uses_the_zip_of_an_entry_with_several_files(tmp_path, monkeypatch):
    asset = {'id': 'opengameart:pack', 'source': 'opengameart', 'source_id': 'pack', 'title': 'Pack', 'type': 'model',
             'license': 'CC0-1.0', 'authors': [], 'attributes': {}, 'downloads': oga.variants_for('model', [
                 {'name': 'scene.blend', 'url': 'https://opengameart.org/sites/default/files/scene.blend', 'size': 10},
                 {'name': 'trees.zip', 'url': 'https://opengameart.org/sites/default/files/trees.zip', 'size': 20}],
                 None)}
    members = [download.remotezip.Member('pine_tree.glb', 0, 0, 4, 4, 0), download.remotezip.Member('rock.glb', 0, 0, 4, 4, 0)]
    monkeypatch.setattr(download.remotezip, 'index', lambda url: members if url.endswith('trees.zip') else pytest.fail(url))
    monkeypatch.setattr(download.remotezip, 'extract', lambda url, member, max_bytes: b'glTF')
    done = download.run(asset, ['all'], str(tmp_path), pick=['pine tree'])
    assert [f['path'] for f in done['files']] == ['pine_tree.glb'] and done['variant']['id'] == 'trees.zip'


@pytest.mark.parametrize('kind, files, want', [
    ('sound', [('flash_bang.wav', 562950)], 'flash_bang.wav'),        # small lossless original
    ('sound', [('big.wav', 30_000_000)], 'preview-ogg'),
    ('music', [('track.wav', 31_000_000)], 'preview-ogg'),            # never a 31 MB WAV by default
    ('music', [('track.wav', 1), ('track.ogg', 1), ('track.mp3', 1)], 'track.ogg'),
    ('music', [('a.ogg', 1), ('b.ogg', 1)], 'all'),                     # an album
    ('sound', [('pack.zip', 1)], 'pack.zip'),
    ('sound', [('hit.wav', 1), ('hit.zip', 1)], 'all'),
    ('music', [('b-loop.ogg', 1), ('b.ogg', 1), ('b-loop.wav', 9), ('b.wav', 9)], 'all-ogg'),  # loop + track
    ('sound', [(f's{i}.wav', 400_000) for i in range(50)], 'all'),   # a pack of effects stays whole
])
def test_opengameart_default_downloads(kind, files, want):
    audio = {'ogg': 'https://opengameart.org/sites/default/files/audio_preview/x.ogg',
             'mp3': 'https://opengameart.org/sites/default/files/x.mp3'}
    variants = oga.variants_for(kind, [{'name': n, 'url': f'https://opengameart.org/sites/default/files/{n}', 'size': s}
                                       for n, s in files], audio)
    assert oga.default_variant(kind, variants) == want


def test_scheduled_job_finds_its_storage_without_app_storage_dir(tmp_path, monkeypatch):
    # The job runner passes DATA_DIR and the app id ($1), not APP_STORAGE_DIR.
    import sync
    monkeypatch.delenv('APP_STORAGE_DIR', raising=False)
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.setenv('APP_JOB_STATE_DIR', str(tmp_path / 'job-state'))
    (tmp_path / 'job-state').mkdir()
    monkeypatch.setattr(sync, 'sync_source', lambda conn, source, log=print, refresh=False: log(f'{source} ok'))
    assert sync.main(['12']) == 0
    assert (tmp_path / 'apps' / '12' / 'catalog' / 'commons.sqlite3').exists()
    assert 'sync finished (0 failed)' in (tmp_path / 'job-state' / 'sync.log').read_text()


# --- Ready-made catalogue (seed) ------------------------------------------------------------------

import gzip  # noqa: E402
import shutil  # noqa: E402

from commons import seed  # noqa: E402


def test_seed_exports_only_public_metadata_and_fills_new_installs(conn, tmp_path, monkeypatch):
    monkeypatch.setenv('APP_STORAGE_DIR', str(tmp_path / 'store'))
    monkeypatch.setattr(seed, 'PACKAGE_DIR', tmp_path / 'no-package-seed')
    music, _ = oga.build('old-amusement-park', oga.parse_item(_oga_page('item_music.html')))
    cards, _ = oga.parse_listing(_oga_page('listing_music.html'))
    with db.transaction(conn):
        catalog.upsert(conn, music)
        catalog.upsert(conn, oga.listing_record(cards[0], 'Music'))                      # cold-0: not read yet
        catalog.upsert(conn, oga.listing_record(cards[1], 'Music'))                      # hidden here
        conn.execute("UPDATE assets SET status='hidden' WHERE id='opengameart:october-jazz'")
        conn.execute("INSERT INTO pulls (asset_id, variant, dest, actor, bytes, at) VALUES "
                     "('opengameart:old-amusement-park', 'all', '/data/projects/private-game', '{}', 1, 'x')")
        conn.execute("INSERT INTO meta (key, value) VALUES ('opengameart_kenney', '[\"skyboxes-space\"]')")
    out = tmp_path / 'seed'
    index = seed.export(conn, out, generated_at='2026-10-09T12:00:00Z')
    assert index['entries'] == 2 and index['read'] == 1 and index['kenney_skip'] == ['skyboxes-space']
    raw = b''.join(gzip.decompress((out / name).read_bytes()) for name in index['parts']).decode()
    assert 'private-game' not in raw and 'october-jazz' not in raw and '"status"' not in raw

    fresh = db.connect(tmp_path / 'fresh.sqlite3')
    shutil.copytree(out, tmp_path / 'store' / seed.STORAGE_DIR / seed.tag(index))
    assert seed.import_newest(fresh, log=lambda *a: None) == {'added': 2}
    assert catalog.get(fresh, 'opengameart:old-amusement-park')['attributes']['details'] == 'complete'
    assert [row[0] for row in fresh.execute('SELECT source_id FROM crawl_queue')] == ['cold-0']
    state = json.loads(fresh.execute("SELECT value FROM meta WHERE key='opengameart_state'").fetchone()[0])
    assert state['new_at'] == '2026-10-09T12:00:00Z' and state['full_at']
    assert seed.import_newest(fresh, log=lambda *a: None) is None  # imported once

    # A later export (from a library that has read more) fills only what this install still lacks.
    cold, _ = oga.build('cold-0', oga.parse_item(_oga_page('item_music.html').replace('Old Amusement Park', 'Cold')))
    with db.transaction(conn):
        catalog.upsert(conn, cold)
    later = seed.export(conn, tmp_path / 'seed2', generated_at='2026-10-11T12:00:00Z')
    shutil.copytree(tmp_path / 'seed2', tmp_path / 'store' / seed.STORAGE_DIR / seed.tag(later))
    assert seed.import_newest(fresh, log=lambda *a: None) == {'filled': 1, 'kept': 1}
    assert catalog.get(fresh, 'opengameart:cold-0')['attributes']['details'] == 'complete'
    assert fresh.execute('SELECT COUNT(*) FROM crawl_queue').fetchone()[0] == 0
    assert not (tmp_path / 'store' / seed.STORAGE_DIR / seed.tag(index)).exists()  # the older seed is removed


def test_seed_splits_into_parts_under_the_storage_seed_limit(conn, tmp_path, monkeypatch):
    monkeypatch.setenv('APP_STORAGE_DIR', str(tmp_path / 'store'))
    monkeypatch.setattr(seed, 'PACKAGE_DIR', tmp_path / 'no-package-seed')
    with db.transaction(conn):
        for number in range(60):
            catalog.upsert(conn, oga.listing_record({'slug': f'entry-{number}', 'title': f'Entry {number}'}, '2D Art'))
    monkeypatch.setattr(seed, 'PART_LIMIT', 600)
    index = seed.export(conn, tmp_path / 'seed', generated_at='2026-10-09T12:00:00Z')
    assert len(index['parts']) > 1 and max(index['bytes']) <= 600
    fresh = db.connect(tmp_path / 'fresh.sqlite3')
    shutil.copytree(tmp_path / 'seed', tmp_path / 'store' / seed.STORAGE_DIR / seed.tag(index))
    assert seed.import_newest(fresh, log=lambda *a: None) == {'added': 60}


def test_a_few_strict_style_matches_come_first_then_close_matches(conn):
    with db.transaction(conn):
        catalog.upsert(conn, {'source': 'kenney', 'source_id': 'toon-rocks', 'type': 'model', 'title': 'Toon Rocks',
                              'license': 'CC0-1.0', 'style': 'stylized', 'tags': ['rock']})
    found = search.search(conn, 'stylized rock')
    ids = [r['id'] for r in found['results']]
    assert ids[0] == 'kenney:toon-rocks' and 'polyhaven:mossy_rock' in ids  # not just the one stylized match
    assert found['notices'] and found['notices'][0].startswith('Only 1 matched the stylized style')
