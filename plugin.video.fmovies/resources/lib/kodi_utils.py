import sys
import json
import xbmc
import xbmcgui
import xbmcaddon
import xbmcplugin

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')
HANDLE = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else -1

def get_setting(setting_id):
    return ADDON.getSetting(setting_id)

def set_setting(setting_id, value):
    ADDON.setSetting(setting_id, str(value))

def notify(message, title="FMovies", icon=xbmcgui.NOTIFICATION_INFO, time_ms=4000):
    xbmcgui.Dialog().notification(title, message, icon, time_ms)

def show_error(message, title="FMovies Error"):
    xbmcgui.Dialog().ok(title, message)

def get_cache_dir():
    """Writable directory for small JSON caches (Kodi profile/cache)."""
    import os
    try:
        import xbmcvfs
        profile = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
    except Exception:
        import tempfile
        profile = os.path.join(tempfile.gettempdir(), 'plugin.video.fmovies')
    cache = os.path.join(profile, 'cache')
    try:
        os.makedirs(cache, exist_ok=True)
    except Exception:
        pass
    return cache


def get_subs_dir():
    """Writable directory for downloaded subtitles (Kodi profile/subs)."""
    import os
    try:
        import xbmcvfs
        profile = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
    except Exception:
        import tempfile
        profile = os.path.join(tempfile.gettempdir(), 'plugin.video.fmovies')
    subs = os.path.join(profile, 'subs')
    try:
        os.makedirs(subs, exist_ok=True)
    except Exception:
        pass
    return subs


def get_search_history():
    raw = get_setting('search_history')
    if not raw:
        return []
    try:
        return json.loads(raw)
    except Exception:
        return []

def add_search_history(query):
    query = query.strip()
    if not query:
        return
    history = get_search_history()
    if query in history:
        history.remove(query)
    history.insert(0, query)
    history = history[:10]  # Keep max 10
    set_setting('search_history', json.dumps(history))

def clear_search_history():
    set_setting('search_history', '')

def build_url(params):
    from urllib.parse import urlencode
    return f"{sys.argv[0]}?{urlencode(params)}"

def add_dir_item(title, params, is_folder=True, is_playable=False, art=None, info=None, context_menu=None):
    url = build_url(params)
    item = xbmcgui.ListItem(label=title)
    
    if is_playable:
        item.setProperty('IsPlayable', 'true')
        
    if art:
        item.setArt(art)
    else:
        item.setArt({
            'icon': ADDON.getAddonInfo('icon'),
            'fanart': ADDON.getAddonInfo('fanart')
        })
        
    if info:
        # Compatibility across Kodi 19/20/21
        try:
            video_info = item.getVideoInfoTag()
            if 'title' in info:
                video_info.setTitle(info['title'])
            if info.get('plot'):
                video_info.setPlot(info['plot'])
            if 'mediatype' in info:
                video_info.setMediaType(info['mediatype'])
            if info.get('genre'):
                genre = info['genre']
                video_info.setGenres(genre if isinstance(genre, list) else [genre])
            if info.get('year'):
                try:
                    video_info.setYear(int(info['year']))
                except (TypeError, ValueError):
                    pass
            if info.get('duration'):
                try:
                    video_info.setDuration(int(info['duration']))
                except (AttributeError, TypeError, ValueError):
                    pass
            if info.get('rating') is not None:
                try:
                    video_info.setRating(float(info['rating']))
                except (AttributeError, TypeError, ValueError):
                    pass
            if info.get('director'):
                try:
                    directors = info['director']
                    video_info.setDirectors(directors if isinstance(directors, list) else [directors])
                except AttributeError:
                    pass
            if info.get('country'):
                try:
                    countries = info['country']
                    video_info.setCountries(countries if isinstance(countries, list) else [countries])
                except AttributeError:
                    pass
            if info.get('cast'):
                try:
                    import xbmcgui as _gui
                    video_info.setCast([_gui.Actor(name) for name in info['cast']])
                except Exception:
                    pass
        except AttributeError:
            pass
        # Legacy fallback so skins always see at least the basics.
        try:
            item.setInfo('video', _legacy_info(info))
        except Exception:
            pass

    _finish_dir_item(item, url, is_folder, context_menu)


def _legacy_info(info):
    """Flatten rich info to the legacy setInfo('video', ...) dict."""
    flat = {}
    for key in ('title', 'plot', 'mediatype', 'genre', 'director', 'country'):
        if info.get(key):
            flat[key] = info[key]
    if info.get('year'):
        flat['year'] = info['year']
    if info.get('duration'):
        flat['duration'] = info['duration']
    if info.get('rating') is not None:
        flat['rating'] = info['rating']
    if info.get('cast'):
        flat['cast'] = info['cast']
    return flat


def _finish_dir_item(item, url, is_folder, context_menu):
    if context_menu:
        item.addContextMenuItems(context_menu)

    xbmcplugin.addDirectoryItem(handle=HANDLE, url=url, listitem=item, isFolder=is_folder)


def end_directory(category=None):
    if category:
        xbmcplugin.setPluginCategory(HANDLE, category)
    xbmcplugin.setContent(HANDLE, 'movies')
    xbmcplugin.endOfDirectory(HANDLE)
