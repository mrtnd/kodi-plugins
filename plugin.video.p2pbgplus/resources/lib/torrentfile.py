"""Minimal bencode decoder (torrent metadata without new dependencies)."""
from __future__ import annotations


def bdecode(data: bytes):
    value, pos = _decode(data, 0)
    return value


def _decode(data: bytes, pos: int):
    token = data[pos:pos + 1]
    if token == b'i':
        end = data.index(b'e', pos)
        return int(data[pos + 1:end]), end + 1
    if token == b'l' or token == b'd':
        items = [] if token == b'l' else {}
        pos += 1
        while data[pos:pos + 1] != b'e':
            if token == b'l':
                value, pos = _decode(data, pos)
                items.append(value)
            else:
                key, pos = _decode(data, pos)
                value, pos = _decode(data, pos)
                items[key] = value
        return items, pos + 1
    if token.isdigit():
        colon = data.index(b':', pos)
        length = int(data[pos:colon])
        start = colon + 1
        return data[start:start + length], start + length
    raise ValueError('invalid bencode at offset {}'.format(pos))


VIDEO_EXTS = ('.mkv', '.mp4', '.avi', '.ts', '.m2ts', '.webm', '.mov', '.wmv')


def file_entries(meta: dict) -> list:
    """Normalized [(path, length)] for single- and multi-file torrents."""
    info = meta.get(b'info', {})
    name = info.get(b'name', b'').decode('utf-8', 'replace')
    if b'files' in info:
        out = []
        for entry in info[b'files']:
            parts = [p.decode('utf-8', 'replace') for p in entry.get(b'path', [])]
            out.append(('/'.join([name] + parts), entry.get(b'length', 0)))
        return out
    return [(name, info.get(b'length', 0))]


def largest_video_index(entries: list) -> int | None:
    """Index of the largest video file, or None when no video file exists."""
    best, best_size = None, -1
    for i, (path, size) in enumerate(entries):
        if path.lower().endswith(VIDEO_EXTS) and size > best_size:
            best, best_size = i, size
    return best
