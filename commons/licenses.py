"""Licence policy: which licences Asset Commons accepts and what each asks of users.

Asset Commons only carries free licences: anything usable commercially and
modifiable. Public-domain dedications (CC0) are preferred and ranked first;
attribution licences are welcome, and the app writes their credit lines for
you. Non-commercial (NC), no-derivatives (ND) and "royalty-free"/personal-use
terms are not open and are refused.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

TIERS = ('public-domain', 'attribution', 'share-alike', 'copyleft')


@dataclass(frozen=True)
class License:
    id: str
    name: str
    short: str
    url: str
    attribution: bool
    share_alike: bool
    tier: str
    summary: str

    def public(self) -> dict:
        data = asdict(self)
        data['attribution_required'] = data.pop('attribution')
        return data


LICENSES: dict[str, License] = {item.id: item for item in [
    License('CC0-1.0', 'Creative Commons Zero 1.0 Universal', 'CC0',
            'https://creativecommons.org/publicdomain/zero/1.0/', False, False, 'public-domain',
            'Public domain. Use, change and sell it without asking or crediting anyone.'),
    License('PDM-1.0', 'Public Domain Mark 1.0', 'Public domain',
            'https://creativecommons.org/publicdomain/mark/1.0/', False, False, 'public-domain',
            'No known copyright. Free for any use.'),
    License('CC-BY-4.0', 'Creative Commons Attribution 4.0', 'CC BY 4.0',
            'https://creativecommons.org/licenses/by/4.0/', True, False, 'attribution',
            'Free for any use, including commercial, as long as you credit the author.'),
    License('CC-BY-3.0', 'Creative Commons Attribution 3.0', 'CC BY 3.0',
            'https://creativecommons.org/licenses/by/3.0/', True, False, 'attribution',
            'Free for any use, including commercial, as long as you credit the author.'),
    License('OGA-BY-3.0', 'OpenGameArt Attribution 3.0', 'OGA-BY 3.0',
            'https://static.opengameart.org/OGA-BY-3.0.txt', True, False, 'attribution',
            'Like CC BY 3.0 without the anti-DRM clause: credit the author.'),
    License('CC-BY-SA-4.0', 'Creative Commons Attribution-ShareAlike 4.0', 'CC BY-SA 4.0',
            'https://creativecommons.org/licenses/by-sa/4.0/', True, True, 'share-alike',
            'Credit the author, and release changed versions of the asset under the same licence.'),
    License('CC-BY-SA-3.0', 'Creative Commons Attribution-ShareAlike 3.0', 'CC BY-SA 3.0',
            'https://creativecommons.org/licenses/by-sa/3.0/', True, True, 'share-alike',
            'Credit the author, and release changed versions of the asset under the same licence.'),
    License('MIT', 'MIT License', 'MIT', 'https://opensource.org/license/mit', True, False, 'attribution',
            'Keep the copyright and licence notice with copies.'),
    License('OFL-1.1', 'SIL Open Font License 1.1', 'OFL 1.1', 'https://openfontlicense.org/', True, False,
            'attribution', 'Fonts: free to use, embed and bundle; keep the notice and do not sell the font alone.'),
    License('GPL-3.0-or-later', 'GNU General Public License 3.0 or later', 'GPL 3.0+',
            'https://www.gnu.org/licenses/gpl-3.0.html', True, True, 'copyleft',
            'Copyleft: a work that includes it must also be released under the GPL, with source.'),
    License('GPL-2.0-or-later', 'GNU General Public License 2.0 or later', 'GPL 2.0+',
            'https://www.gnu.org/licenses/old-licenses/gpl-2.0.html', True, True, 'copyleft',
            'Copyleft: a work that includes it must also be released under the GPL, with source.'),
]}

_ALIASES = {
    'cc0': 'CC0-1.0', 'cc0-1.0': 'CC0-1.0', 'cc0 1.0': 'CC0-1.0', 'cc-0': 'CC0-1.0',
    'public domain': 'PDM-1.0', 'publicdomain': 'PDM-1.0', 'pd': 'PDM-1.0', 'pdm': 'PDM-1.0',
    'cc-by': 'CC-BY-4.0', 'cc by': 'CC-BY-4.0', 'cc-by 4.0': 'CC-BY-4.0', 'cc by 4.0': 'CC-BY-4.0',
    'cc-by-4.0': 'CC-BY-4.0', 'cc-by 3.0': 'CC-BY-3.0', 'cc by 3.0': 'CC-BY-3.0', 'cc-by-3.0': 'CC-BY-3.0',
    'cc-by-sa': 'CC-BY-SA-4.0', 'cc by-sa': 'CC-BY-SA-4.0', 'cc by sa': 'CC-BY-SA-4.0',
    'cc-by-sa 4.0': 'CC-BY-SA-4.0', 'cc by-sa 4.0': 'CC-BY-SA-4.0', 'cc-by-sa-4.0': 'CC-BY-SA-4.0',
    'cc-by-sa 3.0': 'CC-BY-SA-3.0', 'cc by-sa 3.0': 'CC-BY-SA-3.0', 'cc-by-sa-3.0': 'CC-BY-SA-3.0',
    'oga-by': 'OGA-BY-3.0', 'oga-by 3.0': 'OGA-BY-3.0', 'oga-by-3.0': 'OGA-BY-3.0',
    'mit': 'MIT', 'ofl': 'OFL-1.1', 'ofl-1.1': 'OFL-1.1',
    'gpl': 'GPL-3.0-or-later', 'gpl 3.0': 'GPL-3.0-or-later', 'gpl-3.0': 'GPL-3.0-or-later',
    'gpl 2.0': 'GPL-2.0-or-later', 'gpl-2.0': 'GPL-2.0-or-later',
}

_NOT_OPEN = [
    (re.compile(r'\b(nc|non[\s-]?commercial)\b', re.I),
     'Non-commercial licences are not open: Asset Commons only carries assets anyone may use commercially.'),
    (re.compile(r'\b(nd|no[\s-]?deriv\w*)\b', re.I),
     'No-derivatives licences are not open: people must be able to change the asset.'),
    (re.compile(r'royalty[\s-]?free|personal use|editorial|all rights reserved|proprietary', re.I),
     '“Royalty-free” and personal-use terms are not open licences.'),
]


def resolve(value: str | None) -> License | None:
    """The licence for an id or common spelling, or None."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text in LICENSES:
        return LICENSES[text]
    key = re.sub(r'\s+', ' ', text.lower().replace('_', '-'))
    return LICENSES.get(_ALIASES.get(key) or '') or next(
        (item for item in LICENSES.values() if item.id.lower() == key), None)


def refusal(value: str | None) -> str | None:
    """Why a declared licence is not acceptable, or None when it is."""
    if resolve(value):
        return None
    text = value or ''
    for pattern, reason in _NOT_OPEN:
        if pattern.search(text):
            return reason
    return (f'Unknown licence “{text}”. Use one of: '
            + ', '.join(item.short for item in LICENSES.values()) + '.')


def filter_ids(values) -> set[str]:
    """Licence ids selected by a filter of ids, aliases or tier names."""
    if isinstance(values, str):
        values = [part for part in re.split(r'[,|]', values) if part.strip()]
    selected: set[str] = set()
    for value in values or []:
        text = str(value).strip().lower()
        if text in TIERS:
            selected |= {item.id for item in LICENSES.values() if item.tier == text}
        elif text in ('cc-by', 'cc by', 'attribution'):
            selected |= {item.id for item in LICENSES.values() if item.tier == 'attribution'}
        elif text in ('no-attribution', 'no attribution', 'cc0', 'public domain', 'public-domain'):
            selected |= {item.id for item in LICENSES.values() if item.tier == 'public-domain'}
        else:
            found = resolve(text)
            if found:
                selected.add(found.id)
    return selected


def describe(license_id: str) -> dict:
    found = LICENSES.get(license_id)
    if found:
        return found.public()
    return {'id': license_id, 'name': license_id, 'short': license_id, 'url': None,
            'attribution_required': True, 'share_alike': False, 'tier': 'unknown',
            'summary': 'Unrecognised licence: check the source page before use.'}
