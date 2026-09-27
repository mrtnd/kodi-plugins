"""Minimal Kodi helpers, self-contained (no cross-addon imports)."""
import json
import os
import sys

import xbmcaddon
import xbmcgui
import xbmcplugin

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')
HANDLE = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else -1


def get_setting(setting_id):
    return ADDON.getSetting(setting_id)


def log(message):
    """Write to kodi.log so failures can be diagnosed on the device."""
    try:
        import xbmc
        xbmc.log('[P2PBG+] {}'.format(message), xbmc.LOGINFO)
    except Exception:
        pass


def record_error(message):
    """Remember the last failure so Diagnostics can show it on screen."""
    try:
        ADDON.setSetting('last_error', message or '')
    except Exception:
        pass


def get_last_error():
    try:
        return get_setting('last_error')
    except Exception:
        return ''


def notify(message, title='P2PBG'):
    xbmcgui.Dialog().notification(title, message, xbmcgui.NOTIFICATION_INFO, 4000)


def show_blocking(message, title='P2PBG blocked'):
    log(message)
    xbmcgui.Dialog().ok(title, message)


def elementum_present() -> bool:
    try:
        xbmcaddon.Addon('plugin.video.elementum')
        return True
    except Exception:
        return False


def get_profile_dir():
    try:
        import xbmcvfs
        profile = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
    except Exception:
        import tempfile
        profile = os.path.join(tempfile.gettempdir(), 'plugin.video.p2pbgplus')
    try:
        os.makedirs(profile, exist_ok=True)
    except Exception:
        pass
    return profile


def get_search_history():
    try:
        return json.loads(get_setting('search_history') or '')
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
    ADDON.setSetting('search_history', json.dumps(history[:10]))


def clear_search_history():
    ADDON.setSetting('search_history', '')


def build_url(params):
    from urllib.parse import urlencode
    return '{}?{}'.format(sys.argv[0], urlencode(params))


def add_dir_item(title, params, is_folder=True, info=None, art=None):
    url = build_url(params)
    item = xbmcgui.ListItem(label=title)
    if not is_folder:
        item.setProperty('IsPlayable', 'true')
    if art:
        try:
            item.setArt(art)
        except Exception:
            pass
    if info:
        try:
            item.getVideoInfoTag().setTitle(info.get('title', title))
            if info.get('plot'):
                item.getVideoInfoTag().setPlot(info['plot'])
        except AttributeError:
            pass
    xbmcplugin.addDirectoryItem(handle=HANDLE, url=url, listitem=item,
                                isFolder=is_folder)


def add_play_item(title, params, info=None, art=None):
    """Flat playable item: pressing it resolves straight into Elementum."""
    url = build_url(params)
    item = xbmcgui.ListItem(label=title)
    item.setProperty('IsPlayable', 'true')
    if art:
        try:
            item.setArt(art)
        except Exception:
            pass
    if info:
        try:
            tag = item.getVideoInfoTag()
            tag.setTitle(info.get('title', title))
            if info.get('plot'):
                tag.setPlot(info['plot'])
            if info.get('imdb'):
                tag.setIMDBNumber(info['imdb'])
        except AttributeError:
            pass
    xbmcplugin.addDirectoryItem(handle=HANDLE, url=url, listitem=item,
                                isFolder=False)


def resolve_play(uri, title=''):
    """Resolve a playable URI. No endOfDirectory() may follow this."""
    item = xbmcgui.ListItem(label=title, path=uri)
    item.setProperty('IsPlayable', 'true')
    xbmcplugin.setResolvedUrl(HANDLE, True, item)


def end_directory(category=None):
    if category:
        xbmcplugin.setPluginCategory(HANDLE, category)
    xbmcplugin.setContent(HANDLE, 'movies')
    xbmcplugin.endOfDirectory(HANDLE)
