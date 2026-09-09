"""Media sniffing: verify manifests + first segment are real video."""
from __future__ import annotations

from urllib.parse import urljoin

def looks_like_media(head: bytes, content_type: str = '') -> bool:
    ctype = (content_type or '').split(';')[0].strip().lower()
    if ctype.startswith('image/'):
        return False
    if head[:1] == b'\x47' and len(head) >= 188:
        return True  # MPEG-TS sync byte
    if len(head) >= 8 and head[4:8] == b'ftyp':
        return True  # fragmented MP4
    if head[:3] == b'ID3':
        return True
    if ctype.startswith(('video/', 'application/vnd.apple.mpegurl',
                         'application/x-mpegurl', 'audio/')):
        return True
    return False


def playlist_urls(text: str, base: str) -> list[str]:
    urls = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        urls.append(urljoin(base, line))
    return urls


def verify_m3u8(session, url: str, headers: dict | None = None) -> bool:
    """Verify a manifest AND its first media segment (rejects ad-pixel
    poisoned playlists whose segments are 1x1 tracking images)."""
    try:
        res = session.get(url, headers=headers or None, timeout=12)
        if '#EXTM3U' not in res.text[:2000]:
            if looks_like_media(res.content[:8], res.headers.get('content-type', '')):
                return True  # direct media file
            return False
        if '.mp4' in url.split('?')[0]:
            return True
        urls = playlist_urls(res.text, url)
        if not urls:
            return False
        seg_url = urls[0]
        if '#EXT-X-STREAM-INF' in res.text:
            # variant playlist: the first URL is another playlist
            # regardless of its extension. Descend one level.
            vres = session.get(seg_url, headers=headers or None, timeout=12)
            if '#EXTM3U' not in vres.text[:2000]:
                return False
            vurls = playlist_urls(vres.text, seg_url)
            if not vurls:
                return False
            seg_url = vurls[0]
            if '#EXT-X-STREAM-INF' in vres.text:
                return False  # nested variants: give up
        try:
            seg_headers = dict(headers or {})
            seg_headers['Range'] = 'bytes=0-2047'
            sres = session.get(seg_url, headers=seg_headers, timeout=12)
        except Exception:
            return False
        return looks_like_media(sres.content[:2048],
                                sres.headers.get('content-type', ''))
    except Exception:
        return False
