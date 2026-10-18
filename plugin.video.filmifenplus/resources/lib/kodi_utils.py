# -*- coding: utf-8 -*-
"""Thin Kodi adapters: logging, dialogs, list items and directory plumbing.

Kept free of filmifen.com knowledge so the parsers can be tested without
Kodi (tests stub this module's dependencies, not its logic).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
import xbmcvfs

ADDON = xbmcaddon.Addon()
ADDON_ID = 'plugin.video.filmifenplus'
ADDON_NAME = 'FilmiFen+'
HANDLE = int(sys.argv[1]) if len(sys.argv) > 1 and str(sys.argv[1]).isdigit() \
    else -1

_ADDON_PATH = xbmcvfs.translatePath(ADDON.getAddonInfo('path'))

SEARCH_ICON = _ADDON_PATH + '/resources/search.png'
MOVIE_ICON = _ADDON_PATH + '/resources/movie.png'
EMPTY_ICON = _ADDON_PATH + '/resources/empty.png'

# The reference add-on wrote the subtitle file here; kept identical.
SUBTITLE_FILE = xbmcvfs.translatePath('special://temp/filmifen.Bulgarian.srt')

# Router modes (must match main.py). The first four numeric values match
# the reference add-on so stale favourites/bookmarks keep working after
# the fork; the search-screen modes are new.
MODE_LISTING = 1
MODE_SEARCH = 2
MODE_STREAMS = 3
MODE_PLAY = 4
MODE_SEARCH_NEW = 5
MODE_CLEAR_HISTORY = 6

# Search history: JSON file in the add-on profile (same scheme as P2PBG+),
# most recent first, newest entry wins on duplicates.
HISTORY_FILE = 'search_history.json'
MAX_HISTORY = 20

# Kodi has no add-on-level default view; the view is a skin concept, so
# the id depends on the skin. 54 is Estuary's InfoWall
# (View_54_InfoWall.xml, "Media info"). The id is configurable in the
# add-on settings for other skins.
VIEW_INFO_WALL = 54


def log(message):
    try:
        xbmc.log('[%s] %s' % (ADDON_ID, message), xbmc.LOGINFO)
    except Exception:
        pass


def notify(message, heading=ADDON_NAME):
    try:
        xbmcgui.Dialog().notification(heading, message,
                                      xbmcgui.NOTIFICATION_INFO, 4000)
    except Exception:
        pass


def show_error(message, heading=ADDON_NAME):
    log('error: %s' % message)
    notify(message, heading)


def keyboard(heading='Search'):
    """Return the confirmed search text, or None when cancelled."""
    keyb = xbmc.Keyboard('', heading)
    keyb.doModal()
    if keyb.isConfirmed():
        return keyb.getText()
    return None


def profile_dir():
    try:
        path = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
    except Exception:
        path = ''
    return path


def _history_path():
    return os.path.join(profile_dir(), HISTORY_FILE)


def load_history():
    """Remembered search queries, most recent first."""
    path = _history_path()
    try:
        if not xbmcvfs.exists(path):
            return []
        handle = xbmcvfs.File(path, 'r')
        try:
            data = json.loads(handle.read())
        finally:
            handle.close()
    except Exception:
        return []
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def save_history(history):
    profile = profile_dir()
    try:
        if profile and not xbmcvfs.exists(profile):
            xbmcvfs.mkdirs(profile)
        handle = xbmcvfs.File(_history_path(), 'w')
        handle.write(json.dumps(history))
        handle.close()
    except Exception:
        log('could not save search history')


def add_to_history(text):
    text = (text or '').strip()
    if not text:
        return
    history = [item for item in load_history() if item.get('text') != text]
    history.insert(0, {'text': text})
    save_history(history[:MAX_HISTORY])


def clear_history():
    save_history([])
    try:
        xbmc.executebuiltin('Container.Refresh')
    except Exception:
        pass


def _item(name, iconimage='', plot='', playable=False):
    li = xbmcgui.ListItem(name)
    if iconimage:
        li.setArt({'thumb': iconimage, 'poster': iconimage,
                   'banner': iconimage, 'fanart': iconimage})
    info = {'title': name}
    if plot:
        info['plot'] = plot
    li.setInfo(type='Video', infoLabels=info)
    if playable:
        li.setProperty('IsPlayable', 'true')
    return li


def _url(mode, url='', name='', plot='', iconimage='', query=''):
    """Build the plugin query for one directory item.

    ``query`` is only set by the search screen: MODE_SEARCH_NEW with a
    query replays it at once, without one asks via the keyboard. It must
    stay separate from ``name`` (the item label): "New search" is a label,
    not a query.
    """
    params = {
        'url': url or '',
        'mode': mode,
        'name': name or '',
        'plot': plot or '',
        'iconimage': iconimage or '',
    }
    if query:
        params['query'] = query
    return '%s?%s' % (sys.argv[0], urllib.parse.urlencode(params))


def add_dir(name, url, mode, iconimage='', plot='', query=''):
    """Folder entry (menu entries, listings, next page, search screen)."""
    return xbmcplugin.addDirectoryItem(
        handle=HANDLE, url=_url(mode, url, name, plot, iconimage, query),
        listitem=_item(name, iconimage), isFolder=True)


def add_link(name, url, mode, iconimage='', plot=''):
    """Stream-selection entry: a folder that opens the stream list."""
    return xbmcplugin.addDirectoryItem(
        handle=HANDLE, url=_url(mode, url, name, plot, iconimage),
        listitem=_item(name, iconimage, plot=plot, playable=True),
        isFolder=True)


def add_play(name, url, mode, iconimage='', plot=''):
    """A playable stream, not a folder."""
    return xbmcplugin.addDirectoryItem(
        handle=HANDLE, url=_url(mode, url, name, iconimage=iconimage),
        listitem=_item(name, iconimage, plot=plot, playable=True),
        isFolder=False)


def set_content(content='movies'):
    try:
        xbmcplugin.setContent(HANDLE, content)
    except Exception:
        pass


def _setting_bool(key, default):
    try:
        return ADDON.getSettingBool(key)
    except AttributeError:
        value = (ADDON.getSetting(key) or '').strip().lower()
        return default if not value else value == 'true'


def _default_view_id():
    """Configured InfoWall id, or None when the user disabled the view."""
    if not _setting_bool('view_infowall', True):
        return None
    raw = ''
    try:
        raw = (ADDON.getSetting('view_infowall_id') or '').strip()
    except Exception:
        pass
    try:
        return int(raw) if raw else VIEW_INFO_WALL
    except ValueError:
        return VIEW_INFO_WALL


def apply_default_view():
    """Force the InfoWall view on the directory that just closed.

    Executed right after endOfDirectory, because Kodi only accepts a view
    switch for a container that is already listing.
    """
    view_id = _default_view_id()
    if view_id is None:
        return
    try:
        xbmc.executebuiltin('Container.SetViewMode(%d)' % view_id)
    except Exception:
        pass


def end_directory(cache_to_disc=True):
    """Close the directory and apply the default view.

    ``cache_to_disc=False`` for live listings: Kodi must never serve a
    stale copy when the user revisits a section.
    """
    try:
        xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=cache_to_disc)
    except Exception:
        pass
    apply_default_view()
