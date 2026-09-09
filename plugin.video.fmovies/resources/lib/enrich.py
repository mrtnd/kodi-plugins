"""Catalog enrichment: fill items with film-page metadata via 24h cache."""
from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor

from resources.lib.cache import JsonCache

META_CACHE_FILE = 'film_meta.json'
META_CACHE_TTL = 24 * 3600
META_CACHE_MAX = 500

META_FIELDS = ('plot', 'genre', 'cast', 'director', 'country',
               'duration', 'rating', 'fanart')


def _meta_from_details(details, now):
    return {
        '_ts': now,
        'plot': details.get('synopsis', ''),
        'genre': details.get('genres') or [],
        'cast': details.get('actors') or [],
        'director': details.get('directors') or [],
        'country': details.get('countries') or [],
        'duration': details.get('duration'),
        'year': details.get('year'),
        'rating': details.get('rating'),
        'fanart': details.get('backdrop', ''),
    }


def enrich_items(items, cache_dir=None, scraper=None):
    """Fill catalog items with film-page metadata (plot, genre, cast, ...).

    Served from a 24-hour profile cache; misses are fetched concurrently so
    a full catalog page resolves in a few seconds on first visit.
    """
    from resources.lib.scraper import FMoviesScraper
    if not items:
        return items
    if cache_dir is None:
        from resources.lib.kodi_utils import get_cache_dir
        cache_dir = get_cache_dir()
    path = os.path.join(cache_dir, META_CACHE_FILE) if cache_dir else None
    cache = JsonCache(path, ttl=META_CACHE_TTL, max_items=META_CACHE_MAX)
    now = time.time()
    missing = [it for it in items if it.get('url') not in cache.data]
    if missing:
        scraper = scraper or FMoviesScraper()

        def _fetch(item):
            try:
                details = scraper.get_details_and_seasons(item['url'])
                return item['url'], _meta_from_details(details, now)
            except Exception:
                return item['url'], None

        with ThreadPoolExecutor(max_workers=5) as pool:
            for url, meta in pool.map(_fetch, missing):
                if meta:
                    cache.data[url] = meta
        cache.save()
    for item in items:
        meta = cache.data.get(item.get('url')) or {}
        for key in META_FIELDS:
            if meta.get(key) and not item.get(key):
                item[key] = meta[key]
        if meta.get('year') and not item.get('year'):
            item['year'] = meta['year']
    return items
