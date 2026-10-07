"""Outbound HTTP for catalogue feeds and asset downloads.

Only https URLs on an indexed source's hosts are fetched, including every
redirect hop, so a tampered record can never make the service fetch an
internal address. Every request names Asset Commons in its User-Agent, as the
sources' API terms ask.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import USER_AGENT
from .sources import allowed_host


class FetchError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def check_url(url: str) -> str:
    parts = urllib.parse.urlsplit(url or '')
    if parts.scheme != 'https' or not allowed_host(parts.hostname):
        raise FetchError(f'Refusing to fetch {url!r}: not an https URL on an indexed source.')
    return url


class _CheckedRedirects(urllib.request.HTTPRedirectHandler):
    max_redirections = 5

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_CheckedRedirects)


def _open(url: str, timeout: float, headers: dict | None = None):
    request = urllib.request.Request(check_url(url), headers={'User-Agent': USER_AGENT, 'Accept': '*/*',
                                                              **(headers or {})})
    try:
        return _OPENER.open(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        where = urllib.parse.urlsplit(url)
        raise FetchError(f'{where.hostname} answered {exc.code} for {where.path}', exc.code) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise FetchError(f'Could not reach {urllib.parse.urlsplit(url).hostname}: {exc}') from exc


def get_json(url: str, *, timeout: float = 30, max_bytes: int = 64 * 1024 * 1024, headers: dict | None = None):
    with _open(url, timeout, headers) as response:
        body = response.read(max_bytes + 1)
    if len(body) > max_bytes:
        raise FetchError(f'{url} returned more than {max_bytes} bytes.')
    try:
        return json.loads(body)
    except ValueError as exc:
        raise FetchError(f'{url} did not return JSON.') from exc


def get_text(url: str, *, timeout: float = 30, max_bytes: int = 4 * 1024 * 1024) -> str:
    """One web page as text (for sources without an API)."""
    with _open(url, timeout, {'Accept': 'text/html'}) as response:
        body = response.read(max_bytes + 1)
        charset = response.headers.get_content_charset() or 'utf-8'
    if len(body) > max_bytes:
        raise FetchError(f'{url} is larger than {max_bytes} bytes.')
    return body.decode(charset, errors='replace')


def get_range(url: str, start: int, end: int | None = None, *, timeout: float = 30,
              max_bytes: int = 64 * 1024 * 1024) -> tuple[int, int | None, bytes]:
    """Part of a file: (status, total size or None, bytes). A negative start reads the tail."""
    spec = f'bytes={start}' if start < 0 else f'bytes={start}-{"" if end is None else end}'
    with _open(url, timeout, {'Range': spec}) as response:
        body = response.read(max_bytes + 1)
        status = response.status
        content_range = response.headers.get('Content-Range') or ''
    if len(body) > max_bytes:
        raise FetchError(f'{url} returned more than {max_bytes} bytes.')
    total = content_range.rsplit('/', 1)[-1]
    return status, int(total) if total.isdigit() else None, body


def head_size(url: str, *, timeout: float = 15) -> int | None:
    """A file's size from a HEAD request, without downloading it."""
    request = urllib.request.Request(check_url(url), method='HEAD', headers={'User-Agent': USER_AGENT})
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            length = response.headers.get('Content-Length')
    except urllib.error.HTTPError as exc:
        raise FetchError(f'{urllib.parse.urlsplit(url).hostname} answered {exc.code}', exc.code) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise FetchError(f'Could not reach {urllib.parse.urlsplit(url).hostname}: {exc}') from exc
    return int(length) if length and length.isdigit() else None


def get_bytes(url: str, *, timeout: float = 20, max_bytes: int = 4 * 1024 * 1024) -> tuple[bytes, str]:
    with _open(url, timeout) as response:
        body = response.read(max_bytes + 1)
        kind = response.headers.get_content_type()
    if len(body) > max_bytes:
        raise FetchError(f'{url} is larger than {max_bytes} bytes.')
    return body, kind


def download(url: str, path: Path, *, max_bytes: int, md5: str | None = None, timeout: float = 60) -> int:
    """Stream one file to `path` (via a temporary name); returns bytes written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + '.part')
    digest = hashlib.md5(usedforsecurity=False)
    written = 0
    try:
        with _open(url, timeout) as response, open(partial, 'wb') as out:
            while True:
                chunk = response.read(1024 * 256)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_bytes:
                    raise FetchError(f'{path.name} is larger than the {max_bytes // (1024 * 1024)} MB limit.')
                digest.update(chunk)
                out.write(chunk)
        if md5 and digest.hexdigest() != md5.lower():
            raise FetchError(f'{path.name} failed its checksum; the source may have changed. Try again later.')
        os.replace(partial, path)
    finally:
        if partial.exists():
            partial.unlink()
    return written
