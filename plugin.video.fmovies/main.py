import sys
from urllib.parse import parse_qsl
import xbmc
import xbmcgui
import xbmcplugin

from resources.lib.kodi_utils import (
    HANDLE, notify, show_error, get_search_history,
    add_search_history, clear_search_history, add_dir_item, end_directory,
    get_setting, get_subs_dir, get_cache_dir
)
from resources.lib.scraper import FMoviesScraper
from resources.lib.resolver import StreamResolver

META_CACHE_FILE = 'film_meta.json'
META_CACHE_TTL = 7 * 24 * 3600
META_CACHE_MAX = 500


def _load_meta_cache():
    import json
    import os
    import time
    path = os.path.join(get_cache_dir(), META_CACHE_FILE)
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            cache = json.load(fh)
    except Exception:
        return {}, path
    now = time.time()
    fresh = {u: m for u, m in cache.items()
             if isinstance(m, dict) and now - m.get('_ts', 0) < META_CACHE_TTL}
    return fresh, path


def _save_meta_cache(cache, path):
    import json
    if path is None:
        return
    try:
        items = list(cache.items())[-META_CACHE_MAX:]
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(dict(items), fh)
    except Exception:
        pass


def enrich_items(items):
    """Fill catalog items with film-page metadata (plot, genre, cast, ...).

    Served from a 7-day profile cache; misses are fetched concurrently so
    a full catalog page resolves in a few seconds on first visit.
    """
    import time
    from concurrent.futures import ThreadPoolExecutor
    if not items:
        return items
    cache, path = _load_meta_cache()
    now = time.time()
    missing = [it for it in items if it.get('url') not in cache]
    if missing:
        scraper = FMoviesScraper()

        def _fetch(item):
            try:
                details = scraper.get_details_and_seasons(item['url'])
                return item['url'], {
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
            except Exception:
                return item['url'], None

        with ThreadPoolExecutor(max_workers=5) as pool:
            for url, meta in pool.map(_fetch, missing):
                if meta:
                    cache[url] = meta
        _save_meta_cache(cache, path)
    for item in items:
        meta = cache.get(item.get('url')) or {}
        for key in ('plot', 'genre', 'cast', 'director', 'country',
                    'duration', 'rating', 'fanart'):
            if meta.get(key) and not item.get(key):
                item[key] = meta[key]
        if meta.get('year') and not item.get('year'):
            item['year'] = meta['year']
    return items

def main_menu():
    add_dir_item("🔍 Search", {'action': 'search_menu'})
    add_dir_item("🔥 Home Suggestions", {'action': 'catalog', 'url': '/home'})
    add_dir_item("🎬 Movies", {'action': 'catalog', 'url': '/movies'})
    add_dir_item("📺 TV-Series", {'action': 'catalog', 'url': '/tv-series'})
    add_dir_item("⭐ Top IMDb", {'action': 'catalog', 'url': '/top-imdb'})
    add_dir_item("🎭 Genres", {'action': 'dropdown_menu', 'type': 'genre'})
    add_dir_item("🌐 Countries", {'action': 'dropdown_menu', 'type': 'country'})
    end_directory("FMovies Main Menu")

def search_menu():
    add_dir_item("➕ New Search", {'action': 'new_search'})
    history = get_search_history()
    if history:
        for q in history:
            add_dir_item(f"🕒 {q}", {'action': 'search', 'query': q},
                         context_menu=[("Remove from History", f"RunPlugin({sys.argv[0]}?action=clear_history)")])
        add_dir_item("❌ Clear Search History", {'action': 'clear_history'})
    end_directory("Search")

def new_search():
    kb = xbmcgui.Dialog().input("Search FMovies", type=xbmcgui.INPUT_ALPHANUM)
    if kb and kb.strip():
        add_search_history(kb)
        list_search(kb)

def format_duration(total_seconds):
    """7500 -> '2h 5m' for the plot header."""
    try:
        total = int(total_seconds)
    except (TypeError, ValueError):
        return ''
    hours, rest = divmod(total, 3600)
    minutes = rest // 60
    if hours and minutes:
        return f"{hours}h {minutes}m"
    if hours:
        return f"{hours}h"
    if minutes:
        return f"{minutes}m"
    return ''


def build_display_plot(item):
    """Plot text prefixed with a compact info header.

    Most skins only render title + plot in the browse panel, so the key
    facts (genre, cast, director, ...) are folded into the plot head while
    the structured fields stay set for info dialogs.
    """
    lines = []
    if item.get('genre'):
        genre = item['genre']
        lines.append('Genre: {}'.format(
            ', '.join(genre) if isinstance(genre, list) else genre))
    if item.get('cast'):
        cast = item['cast']
        lines.append('Cast: {}'.format(
            ', '.join(cast) if isinstance(cast, list) else cast))
    if item.get('director'):
        director = item['director']
        lines.append('Director: {}'.format(
            ', '.join(director) if isinstance(director, list) else director))
    if item.get('country'):
        country = item['country']
        lines.append('Country: {}'.format(
            ', '.join(country) if isinstance(country, list) else country))
    facts = []
    duration = format_duration(item.get('duration'))
    if duration:
        facts.append(duration)
    if item.get('year'):
        facts.append(str(item['year']))
    if item.get('rating') is not None:
        try:
            facts.append('Rating: {}/10'.format(float(item['rating'])))
        except (TypeError, ValueError):
            pass
    if item.get('quality'):
        facts.append(str(item['quality']))
    if facts:
        lines.append(' | '.join(facts))
    plot = item.get('plot', '') or ''
    if lines and plot:
        return '\n'.join(lines) + '\n\n' + plot
    if lines:
        return '\n'.join(lines)
    return plot


def show_items(items, next_item=None, category="Catalog"):
    for item in items:
        params = {
            'action': 'select_item',
            'url': item['url'],
            'mediatype': item['mediatype'],
            'title': item['raw_title']
        }
        info = {
            'title': item['title'],
            'mediatype': item['mediatype']
        }
        display_plot = build_display_plot(item)
        if display_plot:
            info['plot'] = display_plot
        if item.get('year'):
            try:
                info['year'] = int(item['year'])
            except (TypeError, ValueError):
                pass
        for key in ('plot', 'genre', 'cast', 'director', 'country',
                    'duration', 'rating'):
            if item.get(key) is not None and item.get(key) != []:
                info[key] = item[key]
        art = {'poster': item['thumb'], 'thumb': item['thumb']}
        if item.get('fanart'):
            art['fanart'] = item['fanart']

        is_folder = item['mediatype'] == 'tvshow'
        add_dir_item(
            item['title'],
            params,
            is_folder=is_folder,
            is_playable=not is_folder,
            art=art,
            info=info
        )

    if next_item:
        add_dir_item("▶ Next Page", {'action': 'catalog', 'url': next_item})

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
            info=ep_info
        )
    end_directory(f"{show_title} Episodes")

def play_stream(page_url, title, eps=None):
    from resources.lib.resolver import ResolveError
    resolver = StreamResolver()
    try:
        servers = resolver.get_servers(page_url)
        if not servers:
            notify("No stream servers found.")
            return

        # Preferred server first, then the rest as fallback (like a browser
        # trying each player until one yields a playable stream).
        pref_server = get_setting('preferred_server')
        ordered = sorted(
            servers,
            key=lambda s: (0 if pref_server.lower() in s['name'].lower() else 1),
        )

        try:
            stream_url = resolver.resolve_stream_any(ordered, eps,
                                                     sub_dir=get_subs_dir())
        except ResolveError as e:
            notify(f"Resolve failed: {e}")
            return
        if not stream_url:
            notify("Unable to resolve stream link.")
            return

        base_url, _, header_suffix = stream_url.partition('|')
        play_item = xbmcgui.ListItem(path=base_url)
        play_item.setPath(stream_url)

        # Configure InputStream Adaptive for manifests (hosts use .m3u8,
        # master.txt, extension-less /hls, /pl/ and urlset links).
        # NOTE: the '|Referer=..&User-Agent=..' suffix only covers the
        # manifest request made by Kodi core; inputstream.adaptive fetches
        # media segments itself, so the same headers must also be mirrored
        # into manifest_headers/stream_headers or playback stalls silently.
        is_mp4 = '.mp4' in base_url.split('?')[0]
        is_manifest = not is_mp4 and any(
            marker in base_url
            for marker in ('.m3u8', 'master.txt', '.mpd', '/hls', '/pl/',
                           'streamsvr', 'urlset')
        )
        if get_setting('use_inputstream') == 'true' and is_manifest:
            play_item.setProperty('inputstream', 'inputstream.adaptive')
            play_item.setProperty('inputstream.adaptive.manifest_type', 'hls')
            if header_suffix:
                play_item.setProperty('inputstream.adaptive.manifest_headers', header_suffix)
                play_item.setProperty('inputstream.adaptive.stream_headers', header_suffix)
            try:
                play_item.setMimeType('application/vnd.apple.mpegurl')
                play_item.setContentLookup(False)
            except AttributeError:
                pass

        subtitles = list(getattr(stream_url, 'subtitles', None) or ())
        if subtitles:
            try:
                play_item.setSubtitles(subtitles)
            except AttributeError:
                pass
        try:
            xbmc.log('plugin.video.fmovies: playing {} (subs={})'.format(
                base_url[:120], len(subtitles)), xbmc.LOGINFO)
        except Exception:
            pass

        xbmcplugin.setResolvedUrl(HANDLE, True, play_item)

    except Exception as e:
        show_error(f"Playback error: {e}")

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
