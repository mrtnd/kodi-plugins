"""Tiny TTL JSON file cache (stdlib only, no Kodi dependency)."""
from __future__ import annotations

import json
import time


class JsonCache:
    """Dict-backed JSON cache with TTL expiry and max-size trimming."""

    def __init__(self, path: str | None = None, ttl: int = 24 * 3600,
                 max_items: int = 500):
        self.path = path
        self.ttl = ttl
        self.max_items = max_items
        self.data: dict = self._load()

    def _load(self) -> dict:
        if not self.path:
            return {}
        try:
            with open(self.path, 'r', encoding='utf-8') as fh:
                cache = json.load(fh)
        except Exception:
            return {}
        now = time.time()
        return {u: m for u, m in cache.items()
                if isinstance(m, dict) and now - m.get('_ts', 0) < self.ttl}

    def save(self) -> None:
        if not self.path:
            return
        try:
            items = list(self.data.items())[-self.max_items:]
            with open(self.path, 'w', encoding='utf-8') as fh:
                json.dump(dict(items), fh)
        except Exception:
            pass

    def get(self, key: str) -> dict | None:
        return self.data.get(key)

    def set(self, key: str, value: dict) -> None:
        self.data[key] = value
