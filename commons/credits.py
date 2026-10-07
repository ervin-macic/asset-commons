"""Attribution lines and CREDITS documents.

A credit follows the TASL convention Creative Commons recommends: Title,
Author, Source, Licence. Public-domain assets need no credit, but the CREDITS
document still thanks them so a project keeps a complete provenance record.
"""
from __future__ import annotations

from datetime import date

from .licenses import describe

SOURCE_NAMES = {
    'polyhaven': 'Poly Haven', 'ambientcg': 'ambientCG', 'kenney': 'Kenney', 'quaternius': 'Quaternius',
    'opengameart': 'OpenGameArt', 'freesound': 'Freesound', 'community': 'Asset Commons community',
    'local': 'Asset Commons (local upload)',
}


def author_names(asset: dict) -> str:
    names = [a.get('name') for a in asset.get('authors') or [] if isinstance(a, dict) and a.get('name')]
    if not names:
        return SOURCE_NAMES.get(asset.get('source'), asset.get('source') or 'unknown author')
    if len(names) == 1:
        return names[0]
    return ', '.join(names[:-1]) + ' and ' + names[-1]


def credit_line(asset: dict, *, modified: bool = False) -> str:
    """One plain-text credit line for an asset (TASL)."""
    lic = describe(asset.get('license', ''))
    source = SOURCE_NAMES.get(asset.get('source'), asset.get('source') or '')
    where = f' ({asset["source_url"]})' if asset.get('source_url') else ''
    author = author_names(asset)
    line = f'“{asset.get("title")}” by {author}' + ('' if author == source else f', {source}') + where
    if lic['attribution_required']:
        line += f', licensed under {lic["short"]}'
        if lic.get('url'):
            line += f' ({lic["url"]})'
        if modified:
            line += ', modified'
        return line + '.'
    return line + f' — {lic["short"]}, no attribution required.'


def needs_credit(asset: dict) -> bool:
    return bool(describe(asset.get('license', ''))['attribution_required'])


def credits_markdown(assets: list[dict], *, title: str = 'Credits', today: date | None = None) -> str:
    """A CREDITS.md body grouping assets by what their licence asks."""
    today = today or date.today()
    unique = {a['id']: a for a in assets if isinstance(a, dict) and a.get('id')}
    ordered = sorted(unique.values(), key=lambda a: (str(a.get('title') or '').lower(), a['id']))
    required = [a for a in ordered if needs_credit(a)]
    share_alike = [a for a in required if describe(a.get('license', '')).get('share_alike')]
    public = [a for a in ordered if not needs_credit(a)]
    lines = [f'# {title}', '',
             f'Assets found through Asset Commons. Generated {today.isoformat()}; regenerate with the '
             '`asset_commons_credits` tool after adding assets.', '']
    if required:
        lines += ['## Attribution required', '']
        lines += [f'- {credit_line(a)}' for a in required]
        lines.append('')
    if share_alike:
        lines += ['## Share-alike notice', '',
                  'Changed versions of these assets must be released under the same licence:', '']
        lines += [f'- “{a.get("title")}” ({describe(a.get("license", ""))["short"]})' for a in share_alike]
        lines.append('')
    if public:
        lines += ['## Public domain (CC0), listed with thanks', '',
                  'No attribution is required for these; they are listed to keep a provenance record.', '']
        lines += [f'- {credit_line(a)}' for a in public]
        lines.append('')
    if not ordered:
        lines += ['No assets recorded yet.', '']
    return '\n'.join(lines)
