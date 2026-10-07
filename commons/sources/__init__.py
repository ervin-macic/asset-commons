"""Where assets come from.

Each indexed source has an importer module exposing `fetch_records(log)`
(a generator of catalogue records) and, when its file listings are not part
of the catalogue feed, `fetch_downloads(source_id, asset)`. A source too large
to read in one pass (OpenGameArt) exposes `run(conn, log)` instead: it lists
entries quickly, reads their pages through a queue, and offers
`fetch_record(asset)` for an entry someone needs right away. Live sources
(Freesound) are searched on demand instead of indexed. Planned sources
are listed so the UI and agents can say what is coming, and so their hosts
are not fetched before an importer exists.
"""
from __future__ import annotations

SOURCES = {
    'polyhaven': {
        'name': 'Poly Haven', 'homepage': 'https://polyhaven.com', 'license': 'CC0-1.0',
        'types': ['texture', 'hdri', 'model'], 'status': 'indexed',
        'credit': 'Poly Haven assets and previews come from the Poly Haven API (polyhaven.com).',
        'hosts': ['polyhaven.com', 'polyhaven.org'],
    },
    'ambientcg': {
        'name': 'ambientCG', 'homepage': 'https://ambientcg.com', 'license': 'CC0-1.0',
        'types': ['texture', 'hdri'], 'status': 'indexed',
        'credit': 'ambientCG materials and previews come from the ambientCG API (ambientcg.com).',
        'hosts': ['ambientcg.com', 'struffelproductions.com'],
    },
    'kenney': {
        'name': 'Kenney', 'homepage': 'https://kenney.nl/assets', 'license': 'CC0-1.0',
        'types': ['model', 'sprite', 'ui', 'sound', 'texture'], 'status': 'indexed',
        'credit': 'Packs and previews come from kenney.nl; downloads are Kenney’s own zips. Support Kenney at kenney.nl/support.',
        'hosts': ['kenney.nl'],
    },
    'quaternius': {
        'name': 'Quaternius', 'homepage': 'https://quaternius.com', 'license': 'CC0-1.0',
        'types': ['model', 'animation'], 'status': 'indexed',
        'credit': 'Packs and previews come from quaternius.com; files are free on itch.io (pay what you want).',
        'hosts': ['quaternius.com'],
    },
    'opengameart': {
        'name': 'OpenGameArt', 'homepage': 'https://opengameart.org', 'license': 'CC0-1.0',
        'types': ['sprite', 'music', 'model', 'texture', 'sound', 'ui', 'animation'], 'status': 'indexed',
        'note': 'Community game art: CC0 entries only (2D, music, 3D, textures, sound effects). Licences are '
                'as declared by each uploader.',
        'credit': 'Entries and previews come from opengameart.org, read politely (ten seconds between page '
                  'requests, as its robots.txt asks); files download from OpenGameArt itself.',
        'hosts': ['opengameart.org'],
    },
    'freesound': {
        'name': 'Freesound', 'homepage': 'https://freesound.org', 'license': 'CC0-1.0',
        'types': ['sound'], 'status': 'live',
        'note': 'CC0 sound effects, ambience and music, searched live with your free Freesound API key.',
        'credit': 'Sounds come live from the Freesound API (freesound.org); only sounds someone downloads are kept.',
        'hosts': ['freesound.org'],
    },
}


def allowed_host(host: str | None) -> bool:
    host = (host or '').lower().rstrip('.')
    return any(host == h or host.endswith('.' + h)
               for source in SOURCES.values() for h in source.get('hosts', []))


def importer(source: str):
    if source == 'polyhaven':
        from . import polyhaven
        return polyhaven
    if source == 'ambientcg':
        from . import ambientcg
        return ambientcg
    if source == 'freesound':
        from . import freesound
        return freesound
    if source == 'kenney':
        from . import kenney
        return kenney
    if source == 'quaternius':
        from . import quaternius
        return quaternius
    if source == 'opengameart':
        from . import opengameart
        return opengameart
    return None


def public() -> list[dict]:
    return [{'id': key, **{k: v for k, v in value.items() if k != 'hosts'}} for key, value in SOURCES.items()]
