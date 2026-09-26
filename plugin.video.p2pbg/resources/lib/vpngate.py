"""Fail-closed VPN country gate (no extra infra, on-device check)."""
from __future__ import annotations

import time

CHECK_URL = 'https://ipinfo.io/json'
CHECK_TIMEOUT = 8


def parse_country(payload) -> str:
    """Country code from an ipinfo-style payload, '' when unknown."""
    if not isinstance(payload, dict):
        return ''
    country = payload.get('country') or ''
    return str(country).strip().upper()


class VPNGate:
    """Caches the last geo check; every playback revalidates when stale."""

    def __init__(self, session=None, country='BG', cache_ttl=300):
        self.session = session
        self.country = (country or 'BG').strip().upper()
        self.cache_ttl = cache_ttl
        self._ts = 0.0
        self._ok = False
        self._label = ''

    def check(self) -> tuple:
        """(ok, label). Fail-closed: any error means not-ok."""
        now = time.time()
        if now - self._ts < self.cache_ttl:
            return self._ok, self._label
        ok, label = False, 'check failed'
        try:
            res = self._get(CHECK_URL)
            country = parse_country(res.json())
            label = country or 'unknown'
            ok = country == self.country
        except Exception:
            ok, label = False, 'check failed'
        self._ts, self._ok, self._label = now, ok, label
        return ok, label

    def _get(self, url):
        if self.session is not None:
            return self.session.get(url, timeout=CHECK_TIMEOUT)
        import requests
        return requests.get(url, timeout=CHECK_TIMEOUT,
                            headers={'User-Agent': 'Kodi-p2pbg-gate'})
