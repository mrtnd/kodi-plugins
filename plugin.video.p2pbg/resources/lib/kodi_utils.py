"""Minimal Kodi helpers, self-contained (no cross-addon imports)."""
import json
import os
import sys

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')
HANDLE = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else -1


def get_setting(setting_id):
    return ADDON.getSetting(setting_id)


def notify(message, title='P2PBG'):
    xbmcgui.Dialog().notification(title, message, xbmcgui.NOTIFICATION_INFO, 4000)


def show_blocking(message, title='P2PBG blocked'):
    xbmcgui.Dialog().ok(title, message)


def elementum_present() -> bool:
    try:
        xbmcaddon.Addon('plugin.video.elementum')
        return True
    except Exception:
        return False


def _profile_subdir(name):
    try:
        import xbmcvfs
        profile = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
    except Exception:
        import tempfile
        profile = os.path.join(tempfile.gettempdir(), 'plugin.video.p2pbg')
    path = os.path.join(profile, name)
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass
    return path


def get_torrents_dir():
    return _profile_subdir('torrents')


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


def add_dir_item(title, params, is_folder=True, info=None):
    url = build_url(params)
    item = xbmcgui.ListItem(label=title)
    if not is_folder:
        item.setProperty('IsPlayable', 'true')
    if info:
        try:
            item.getVideoInfoTag().setTitle(info.get('title', title))
            if info.get('plot'):
                item.getVideoInfoTag().setPlot(info['plot'])
        except AttributeError:
            pass
    xbmcplugin.addDirectoryItem(handle=HANDLE, url=url, listitem=item,
                                isFolder=is_folder)


def end_directory(category=None):
    if category:
        xbmcplugin.setPluginCategory(HANDLE, category)
    xbmcplugin.setContent(HANDLE, 'movies')
    xbmcplugin.endOfDirectory(HANDLE)
