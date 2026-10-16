# -*- coding: utf-8 -*-
"""Thin Kodi adapters: settings, logging, dialogs, history and list items.

Kept free of tracker knowledge so it can be stubbed in tests.
"""
from __future__ import annotations

import json
import os
import sys

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
import xbmcvfs

ADDON = xbmcaddon.Addon()
ADDON_ID = 'plugin.video.p2pbgplus'
HANDLE = int(sys.argv[1]) if len(sys.argv) > 1 and str(sys.argv[1]).isdigit() else -1

# Setting ids (must match resources/settings.xml).
S_USER = 'p2pbg_user'
S_PASSWORD = 'p2pbg_password'
S_PREFER_BGAUDIO = 'prefer_bgaudio'
S_SHOW_XXX = 'show_xxx'
S_VPN_COUNTRY = 'vpn_country'
S_FIRSTRUN = 'firstrun'
S_SEARCH_HISTORY = 'search_history'
S_LAST_ERROR = 'last_error'
S_LAST_PLAY = 'last_play'
S_LAST_LISTING = 'last_listing'
S_LAST_CATEGORY = 'last_category'
S_LAST_CALL = 'last_call'
S_LAST_TABLE = 'last_table'
S_LAST_ITEMS = 'last_items'

HISTORY_FILE = 'search_history.json'
MAX_HISTORY = 20


def get_setting(setting_id, default=''):
    try:
        value = ADDON.getSetting(setting_id)
    except Exception:
        return default
    return value if value != '' else default


def set_setting(setting_id, value):
    try:
        ADDON.setSetting(setting_id, str(value) if value is not None else '')
    except Exception:
        pass


def get_bool(setting_id, default=False):
    raw = get_setting(setting_id)
    if raw == '':
        return default
    return raw.lower() == 'true'


def log(message):
    try:
        xbmc.log('[P2PBG+] ' + str(message), xbmc.LOGINFO)
    except Exception:
        pass


def notify(message, title='P2PBG+'):
    try:
        xbmcgui.Dialog().notification(title, message)
    except Exception:
        log('notify: ' + str(message))


def show_error(message, title='P2PBG+'):
    """Unmissable reason why something did not start."""
    log(message)
    set_setting(S_LAST_ERROR, message)
    try:
        xbmcgui.Dialog().ok(title, message)
    except Exception:
        pass


def profile_dir():
    try:
        path = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
    except Exception:
        path = ''
    return path


def _history_path():
    return os.path.join(profile_dir(), HISTORY_FILE)


def load_history():
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


def build_url(params):
    """Compact plugin URL; ';' in categories stays literal."""
    from urllib.parse import quote_plus
    parts = []
    for key in ('m', 'c', 'q', 'u', 'n', 'bare'):
        value = params.get(key)
        if value in (None, ''):
            continue
        if key in ('q', 'u', 'n'):
            value = quote_plus(str(value))
        parts.append(key + '=' + str(value))
    return sys.argv[0] + '?' + '&'.join(parts)


def add_item(label, url, icon, is_folder=True, plot='', imdb_id='',
             playable=False):
    item = xbmcgui.ListItem(label)
    item.setArt({'thumb': icon, 'poster': icon, 'banner': icon,
                 'fanart': icon})
    if playable:
        item.setProperty('IsPlayable', 'true')
    try:
        item.setInfo(type='Video',
                     infoLabels={'Title': label, 'plot': plot,
                                 'IMDBNumber': imdb_id or ''})
    except Exception:
        pass
    if icon:
        item.setProperty('fanart_image', icon)
    xbmcplugin.addDirectoryItem(handle=HANDLE, url=url, listitem=item,
                                isFolder=is_folder)
    return True


def add_folder(label, params, icon):
    params = dict(params)
    params.setdefault('n', label)
    return add_item(label, build_url(params), icon, is_folder=True)


def add_playable(label, url, icon, plot='', imdb_id=''):
    return add_item(label, url, icon, is_folder=False, plot=plot,
                    imdb_id=imdb_id, playable=True)


def end_directory(cache_to_disc=False):
    xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=cache_to_disc)
