# -*- coding: utf-8 -*-
"""Thin Kodi adapters: logging, dialogs, list items and directory plumbing.

Kept free of filmifen.com knowledge so the parsers can be tested without
Kodi (tests stub this module's dependencies, not its logic).
"""
from __future__ import annotations

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

# The reference add-on wrote the subtitle file here; kept identical.
SUBTITLE_FILE = xbmcvfs.translatePath('special://temp/filmifen.Bulgarian.srt')

# Router modes (must match main.py). Numeric values match the reference
# add-on so stale favourites/bookmarks keep working after the fork.
MODE_LISTING = 1
MODE_SEARCH = 2
MODE_STREAMS = 3
MODE_PLAY = 4


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


def _url(mode, url='', name='', plot='', iconimage=''):
    """Build the plugin query for one directory item."""
    query = urllib.parse.urlencode({
        'url': url or '',
        'mode': mode,
        'name': name or '',
        'plot': plot or '',
        'iconimage': iconimage or '',
    })
    return '%s?%s' % (sys.argv[0], query)


def add_dir(name, url, mode, iconimage='', plot=''):
    """Folder entry (menu entries, listings, next page)."""
    return xbmcplugin.addDirectoryItem(
        handle=HANDLE, url=_url(mode, url, name, plot, iconimage),
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


def end_directory(cache_to_disc=True):
    """Close the directory.

    ``cache_to_disc=False`` for live listings: Kodi must never serve a
    stale copy when the user revisits a section.
    """
    try:
        xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=cache_to_disc)
    except Exception:
        pass
