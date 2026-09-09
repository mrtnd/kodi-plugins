"""Kodi entry point: thin router, views/playback live in resources.lib."""
import sys
from urllib.parse import parse_qsl

from resources.lib.enrich import enrich_items as _enrich_items
from resources.lib.info import build_display_plot, format_duration
from resources.lib.kodi_utils import clear_search_history, get_cache_dir, notify
from resources.lib.playback import play_stream
from resources.lib.views import (
    dropdown_menu, list_catalog, list_episodes, list_search,
    main_menu, new_search, search_menu, select_item, show_items,
)

# Re-exported so existing imports (and tests) keep working.
# enrich_items wrapper resolves the cache dir via this module's
# get_cache_dir so callers/tests can patch main.get_cache_dir.
def enrich_items(items, cache_dir=None, scraper=None):
    if cache_dir is None:
        cache_dir = get_cache_dir()
    return _enrich_items(items, cache_dir=cache_dir, scraper=scraper)


__all__ = [
    'enrich_items', 'build_display_plot', 'format_duration',
    'main_menu', 'search_menu', 'new_search', 'show_items',
    'list_catalog', 'list_search', 'dropdown_menu', 'select_item',
    'list_episodes', 'play_stream', 'router',
]


def router(paramstring):
    params = dict(parse_qsl(paramstring[1:]))
    action = params.get('action')

    if action == 'catalog':
        list_catalog(params.get('url'))
    elif action == 'search_menu':
        search_menu()
    elif action == 'new_search':
        new_search()
    elif action == 'search':
        list_search(params.get('query'))
    elif action == 'clear_history':
        clear_search_history()
        notify("Search history cleared.")
    elif action == 'dropdown_menu':
        dropdown_menu(params.get('type'))
    elif action == 'select_item':
        select_item(params.get('url'), params.get('mediatype'), params.get('title'))
    elif action == 'episodes':
        list_episodes(params.get('season_id'), params.get('show_title'))
    elif action == 'play':
        play_stream(params.get('url'), params.get('title'), params.get('eps'))
    else:
        main_menu()


if __name__ == '__main__':
    router(sys.argv[2] if len(sys.argv) > 2 else '')
