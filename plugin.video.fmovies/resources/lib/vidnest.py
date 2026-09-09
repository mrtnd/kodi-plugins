"""Vidnest server catalogue, payload decoding, stream normalization."""
from __future__ import annotations

import base64
import json

VIDNEST_API = 'https://new.vidnest.fun'
# Custom base64 alphabet used by vidnest's decryptCipherResponse
VIDNEST_B64 = 'RB0fpH8ZEyVLkv7c2i6MAJ5u3IKFDxlS1NTsnGaqmXYdUrtzjwObCgQP94hoeW+/='
_STD_B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/='

# Vidnest servers, in the same order/preference as the vidnest web UI
VIDNEST_SERVERS = (
    ('rogflix', 'movie'),            # filxer: {"url": ...}
    ('videasy', 'movie'),            # alfa: {"url": ..., "headers": {...}}
    ('vidrock', 'movie'),            # prime: {"sources": [...]}
    ('vidzee', 'movie'),             # gama: {"streams": [...]}
    ('vidxyz', 'movie'),             # beta: {"streams": [...]}
    ('klikxxi', 'movie'),            # ophim: {"sources": [...]}
    ('buzz', 'movie'),               # catflix: {"url": ..., "headers": {...}}
    ('nextgencloudfabric', 'movie'),  # zeta: {"url", "all_urls": [...]}
    ('hollymoviehd', 'movie'),       # sigma: {"streams": [...]}
)


def decode_payload(data: str) -> bytes:
    """Decode vidnest's custom-alphabet base64 payload."""
    std = data.translate(str.maketrans(VIDNEST_B64, _STD_B64))
    return base64.b64decode(std)


# Back-compat alias.
vidnest_decode = decode_payload


def maybe_decrypt(payload: dict) -> dict:
    if isinstance(payload, dict) and payload.get('encrypted'):
        try:
            return json.loads(decode_payload(payload['data']).decode())
        except Exception:
            pass
    return payload


def build_url(server: str, kind: str, vid: str,
              season: str | None = None, episode: str | None = None) -> str:
    if kind == 'tv' and season and episode:
        return '{}/{}/tv/{}/{}/{}'.format(VIDNEST_API, server, vid, season, episode)
    return '{}/{}/{}/{}'.format(VIDNEST_API, server, kind, vid)


def extract_streams(payload: dict) -> list[tuple[str, dict]]:
    """Normalize per-server vidnest response shapes to [(url, headers)]."""
    if not isinstance(payload, dict):
        return []
    fallback_headers = payload.get('headers') or {}
    if payload.get('referer') and 'Referer' not in fallback_headers:
        fallback_headers = dict(fallback_headers, Referer=payload['referer'])
    out: list[tuple[str, dict]] = []
    if payload.get('url'):
        out.append((payload['url'], fallback_headers))
    for key in ('streams', 'sources', 'all_urls'):
        items = payload.get(key)
        if isinstance(items, list):
            for it in items:
                if isinstance(it, dict) and it.get('url'):
                    out.append((it['url'], it.get('headers') or fallback_headers))
                elif isinstance(it, str) and it.startswith('http'):
                    out.append((it, fallback_headers))
    # prefer hls manifests
    out.sort(key=lambda u: (0 if 'm3u8' in u[0] else 1))
    return out
