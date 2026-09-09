"""Netoda token codec (AES-GCM + PBKDF2, mirrors app-single.min.js)."""
from __future__ import annotations

import base64
import hashlib
import os
import time

from resources.lib.aesgcm import gcm_encrypt, gcm_decrypt


def pbkdf2_key(salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac('sha256', b'player', salt, 1000, 32)


# Back-compat alias (tests import _pbkdf2_key from resolver).
_pbkdf2_key = pbkdf2_key


def _b64url_encode(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip('=')


def build_watch_fragment(mid: str, eps: str, srv: str, loc: str,
                         ts: int | None = None) -> str:
    """Build the netoda #watch fragment exactly like app-single.min.js be()."""
    ts = ts if ts is not None else int(time.time())
    plain = '{}+{}+{}+{}+{}'.format(mid, eps, srv, loc, ts).encode()
    key = hashlib.sha256(loc.encode()).digest()
    iv = os.urandom(12)
    ct, tag = gcm_encrypt(key, iv, plain)
    token = base64.b64encode(iv + ct + tag).decode()
    return _b64url_encode(token)


def build_get_path(mid: str, eps: str, srv: str,
                   ts: int | None = None) -> str:
    """Build the netoda /get/{salt}-{iv}-{ct} path."""
    ts = ts if ts is not None else int(time.time())
    plain = '{}+{}+{}+{}'.format(mid, eps, srv, ts).encode()
    salt = os.urandom(8)
    key = pbkdf2_key(salt)
    iv = os.urandom(12)
    ct, tag = gcm_encrypt(key, iv, plain)
    return '{}-{}-{}'.format(salt.hex(), iv.hex(), (ct + tag).hex())


def decrypt_info(info: str) -> str:
    """Decrypt a netoda /get/ `info` token -> e.g. 'movie/1443200-1788798062'."""
    salt_hex, iv_hex, ct_hex = info.split('-')
    key = pbkdf2_key(bytes.fromhex(salt_hex))
    data = bytes.fromhex(ct_hex)
    return gcm_decrypt(key, bytes.fromhex(iv_hex), data[:-16], data[-16:]).decode()


# Back-compat names used by resolver/tests.
netoda_hash = build_watch_fragment
netoda_get_path = build_get_path
netoda_decrypt_info = decrypt_info
