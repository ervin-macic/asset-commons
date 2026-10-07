"""Polite pacing for sites that ask crawlers to wait between requests.

OpenGameArt's robots.txt asks for ten seconds between requests. The sync job
and the app service are separate processes, so the next free moment for each
host is kept in a small file in the app's storage, guarded by an exclusive
lock. A caller claims a slot under the lock (possibly a few seconds ahead),
releases the lock and sleeps until its slot, so no two requests to the host
start closer together than the interval asked for.
"""
from __future__ import annotations

import fcntl
import os
import re
import time
from pathlib import Path


class Busy(Exception):
    """The host's next free slot is further away than the caller can wait."""

    def __init__(self, delay: float):
        super().__init__(f'the next polite request slot is {delay:.0f} s away')
        self.delay = delay


def _path(host: str) -> Path:
    root = os.environ.get('APP_STORAGE_DIR')
    base = Path(root) / 'catalog' if root else Path('/tmp/asset-commons-pace')
    base.mkdir(parents=True, exist_ok=True)
    return base / f'pace-{re.sub(r"[^a-z0-9.-]", "_", host.lower())}'


def wait(host: str, interval: float, *, max_wait: float | None = None, sleep=time.sleep, clock=time.time) -> float:
    """Wait until `interval` seconds after the host's previous request; returns seconds waited.

    Raises Busy (without claiming a slot) when the wait would exceed `max_wait`.
    """
    with open(_path(host), 'a+', encoding='utf-8') as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.seek(0)
        try:
            last = float(handle.read().strip() or 0)
        except ValueError:
            last = 0.0
        now = clock()
        slot = max(now, last + interval)
        delay = slot - now
        if max_wait is not None and delay > max_wait:
            raise Busy(delay)
        handle.seek(0)
        handle.truncate()
        handle.write(repr(slot))
        handle.flush()
    if delay > 0:
        sleep(delay)
    return delay
