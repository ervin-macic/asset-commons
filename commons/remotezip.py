"""Read inside a remote zip without downloading all of it.

A zip keeps its table of contents (the central directory) at the end of the
file, so one HTTP range request for the last few kilobytes lists every file in
a pack, and one more range request per member fetches just that file. Servers
that ignore ranges get the whole archive instead (still size-limited).
"""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass

from . import net

TAIL = 64 * 1024


@dataclass(frozen=True)
class Member:
    name: str
    method: int
    crc: int
    compressed: int
    size: int
    offset: int


def _parse_directory(data: bytes) -> list[Member]:
    members, p = [], 0
    while p + 46 <= len(data) and data[p:p + 4] == b'PK\x01\x02':
        method, = struct.unpack('<H', data[p + 10:p + 12])
        crc, compressed, size = struct.unpack('<III', data[p + 16:p + 28])
        name_len, extra_len, comment_len = struct.unpack('<HHH', data[p + 28:p + 34])
        offset, = struct.unpack('<I', data[p + 42:p + 46])
        name = data[p + 46:p + 46 + name_len].decode('utf-8', 'replace')
        members.append(Member(name, method, crc, compressed, size, offset))
        p += 46 + name_len + extra_len + comment_len
    return members


def index(url: str) -> list[Member]:
    """Every member of a remote zip, from its central directory."""
    status, total, tail = net.get_range(url, -TAIL)
    end = tail.rfind(b'PK\x05\x06')
    if end < 0:
        raise net.FetchError('Not a zip file, or its index is not at the end.')
    _entries, size, offset = struct.unpack('<HII', tail[end + 10:end + 20])
    if status != 206 or total is None:  # the whole file came back
        return _parse_directory(tail[offset:offset + size])
    start = offset - (total - len(tail))
    directory = tail[start:start + size] if start >= 0 else net.get_range(url, offset, offset + size - 1)[2]
    return _parse_directory(directory)


def extract(url: str, member: Member, *, max_bytes: int) -> bytes:
    """One member's bytes via a range request, checked against its CRC."""
    if member.size > max_bytes:
        raise net.FetchError(f'{member.name} is larger than the size limit.')
    head = 30 + len(member.name.encode()) + 1024  # local header; its extra field may differ in length
    status, _total, chunk = net.get_range(url, member.offset, member.offset + head + member.compressed)
    if status != 206:
        raise net.FetchError('The server does not support partial downloads.')
    if chunk[:4] != b'PK\x03\x04':
        raise net.FetchError(f'Unexpected data for {member.name}.')
    name_len, extra_len = struct.unpack('<HH', chunk[26:30])
    data = chunk[30 + name_len + extra_len:30 + name_len + extra_len + member.compressed]
    if member.method == 8:
        data = zlib.decompressobj(-15).decompress(data)
    elif member.method != 0:
        raise net.FetchError(f'{member.name} uses an unsupported compression method.')
    if zlib.crc32(data) & 0xFFFFFFFF != member.crc:
        raise net.FetchError(f'{member.name} failed its checksum.')
    return data
