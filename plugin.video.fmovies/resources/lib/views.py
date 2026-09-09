"""Kodi list views: menus, catalog, search, episodes (no playback)."""
from __future__ import annotations

import sys

import xbmcgui

from resources.lib.enrich import enrich_items
from resources.lib.info import build_display_plot
from resources.lib.kodi_utils import (
    add_dir_item, add_search_history, clear_search_history, end_directory,
    get_search_history, show_error, notify,
)
from resources.lib.scraper import FMoviesScraper

INFO_KEYS = ('plot', 'genre', 'cast', 'director', 'country', 'duration', 'rating')


def main_menu():
    add_dir_item("Search", {'action': 'search_menu'})
    add_dir_item("Home Suggestions", {'action': 'catalog', 'url': '/home'})
    add_dir_item("Movies", {'action': 'catalog', 'url': '/movies'})
    add_dir_item("TV-Series", {'action': 'catalog', 'url': '/tv-series'})
    add_dir_item("Top IMDb", {'action': 'catalog', 'url': '/top-imdb'})
    add_dir_item("Genres", {'action': 'dropdown_menu', 'type': 'genre'})
    add_dir_item("Countries", {'action': 'dropdown_menu', 'type': 'country'})
    end_directory("FMovies Main Menu")


def search_menu():
    add_dir_item("New Search", {'action': 'new_search'})
    history = get_search_history()
    if history:
        for q in history:
            add_dir_item(q, {'action': 'search', 'query': q},
                         context_menu=[("Remove from History",
                                        f"RunPlugin({sys.argv[0]}?action=clear_history)")])
        add_dir_item("Clear Search History", {'action': 'clear_history'})
    end_directory("Search")


def new_search():
    kb = xbmcgui.Dialog().input("Search FMovies", type=xbmcgui.INPUT_ALPHANUM)
    if kb and kb.strip():
        add_search_history(kb)
        list_search(kb)


def show_items(items, next_item=None, category="Catalog"):
    for item in items:
        params = {
            'action': 'select_item',
            'url': item['url'],
            'mediatype': item['mediatype'],
            'title': item['raw_title'],
        }
        info = {'title': item['title'], 'mediatype': item['mediatype']}
        display_plot = build_display_plot(item)
        if display_plot:
            info['plot'] = display_plot
        if item.get('year'):
            try:
                info['year'] = int(item['year'])
            except (TypeError, ValueError):
                pass
        for key in INFO_KEYS:
            if item.get(key) is not None and item.get(key) != []:
                info[key] = item[key]
        art = {'poster': item['thumb'], 'thumb': item['thumb']}
        if item.get('fanart'):
            art['fanart'] = item['fanart']

        is_folder = item['mediatype'] == 'tvshow'
        add_dir_item(item['title'], params, is_folder=is_folder,
                     is_playable=not is_folder, art=art, info=info)

    if next_item:
        add_dir_item("Next Page >>", {'action': 'catalog', 'url': next_item})

    end_directory(category)


def list_catalog(url):
    scraper = FMoviesScraper()
    try:
        items, next_page = scraper.get_catalog(url)
    except Exception as e:
        show_error(f"Failed to load catalog: {e}")
        return
    show_items(enrich_items(items), next_page)


def list_search(query, limit=40):
    scraper = FMoviesScraper()
    try:
        items, _next = scraper.search(query, limit=limit)
    except Exception as e:
        show_error(f"Search failed: {e}")
        return
    if not items:
        notify("No results found.")
        end_directory(f"Search: {query}")
        return
    show_items(enrich_items(items), category=f"Search: {query}")


def dropdown_menu(category_type):
    scraper = FMoviesScraper()
    try:
        items = scraper.get_dropdown_items(category_type)
    except Exception as e:
        show_error(f"Failed to load {category_type}s: {e}")
        return
    for item in items:
        add_dir_item(item['title'], {'action': 'catalog', 'url': item['url']})
    end_directory(f"Browse {category_type.title()}s")


def select_item(url, mediatype, title):
    from resources.lib.playback import play_stream
    scraper = FMoviesScraper()
    try:
        details = scraper.get_details_and_seasons(url)
    except Exception as e:
        show_error(f"Failed to load details: {e}")
        return

    episodes = details.get('episodes') or []
    # Authoritative series check: the film page itself declares
    # data-mode="serie", catching series misclassified as movies.
    is_series = mediatype == 'tvshow' or details.get('mode') == 'serie'
    series_info = {
        'plot': details.get('synopsis', ''),
        'genre': details.get('genres') or [],
        'cast': details.get('actors') or [],
        'director': details.get('directors') or [],
        'country': details.get('countries') or [],
        'duration': details.get('duration'),
        'year': details.get('year'),
        'rating': details.get('rating'),
    }
    series_art = {}
    if details.get('backdrop'):
        series_art['fanart'] = details['backdrop']
    if is_series and len(episodes) > 1:
        list_episodes(url, title, episodes, info=series_info, art=series_art)
    elif is_series and len(episodes) == 1:
        play_stream(url, title, episodes[0]['num'])
    else:
        # Direct play for movie
        play_stream(url, title)


def list_episodes(page_url, show_title, episodes=None, info=None, art=None):
    if episodes is None:
        scraper = FMoviesScraper()
        try:
            episodes = scraper.get_episodes(page_url)
        except Exception as e:
            show_error(f"Failed to load episodes: {e}")
            return

    for ep in episodes:
        ep_info = dict(info or {})
        ep_info.setdefault('title', f"{show_title} - {ep['title']}")
        ep_info.setdefault('mediatype', 'episode')
        add_dir_item(
            f"{show_title} - {ep['title']}",
            {'action': 'play', 'url': page_url, 'eps': ep['num'], 'title': ep['title']},
            is_folder=False,
            is_playable=True,
            art=art,
            info=ep_info,
        )
    end_directory(f"{show_title} Episodes")
