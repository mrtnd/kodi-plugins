"""Kodi entry point: categories, search, catalog, VPN-gated Elementum play."""
import sys
from urllib.parse import parse_qsl

import xbmcgui

from resources.lib.kodi_utils import (
    add_dir_item, add_search_history, clear_search_history, end_directory,
    get_search_history, get_setting, notify,
)
from resources.lib.p2pbg import AuthError, CATEGORIES, P2PBGClient
from resources.lib.playback import (
    list_catalog, list_files, play_torrent, search_and_show,
)


def _client():
    return P2PBGClient(
        base_url=get_setting('base_url') or 'https://www.p2pbg.com',
        username=get_setting('p2pbg_user'),
        password=get_setting('p2pbg_password'))


def _prefs():
    return {
        'bgaudio': get_setting('prefer_bgaudio') == 'true',
        'show_xxx': get_setting('show_xxx') == 'true',
    }


def main_menu():
    import datetime
    year = datetime.date.today().year
    _first_run_check()
    add_dir_item('Търсене', {'action': 'search_menu'})
    add_dir_item('Последно добавени', {'action': 'catalog',
                                       'url': 'latest'})
    for offset in range(3):
        add_dir_item('Филми от {} година'.format(year - offset),
                     {'action': 'search', 'query': str(year - offset)})
    for cat_id, cat_name in CATEGORIES:
        add_dir_item(cat_name, {'action': 'catalog',
                                'url': 'cat:' + cat_id})
    end_directory('P2PBG+ Torrents')


def _first_run_check():
    import xbmcaddon
    addon = xbmcaddon.Addon()
    try:
        first = addon.getSetting('firstrun') != 'false'
    except Exception:
        first = False
    if first and not get_setting('p2pbg_user'):
        notify('Въведете потребител и парола в Настройки.')
        addon.openSettings()
    try:
        addon.setSetting('firstrun', 'false')
    except Exception:
        pass


def _catalog_url(spec):
    from urllib.parse import urlencode
    prefs = _prefs()
    params = {'active': '1', 'hidexxx': 'off' if prefs['show_xxx'] else 'on'}
    if prefs['bgaudio']:
        params['bgaudio'] = '1'
    if spec == 'latest':
        base = '/torrents'
    elif spec.startswith('cat:'):
        params['category'] = spec[4:]
        base = '/torrents'
    else:
        return spec  # next-page absolute URL
    return _client().base_url + base + '?' + urlencode(params)


def search_menu():
    add_dir_item('New Search', {'action': 'new_search'})
    for query in get_search_history():
        add_dir_item(query, {'action': 'search', 'query': query})
    add_dir_item('Clear Search History', {'action': 'clear_history'})
    end_directory('Search')


def new_search():
    kb = xbmcgui.Dialog().input('Search p2pbg', type=xbmcgui.INPUT_ALPHANUM)
    if kb and kb.strip():
        add_search_history(kb)
        search_and_show(_client(), kb)


def router(paramstring):
    params = dict(parse_qsl(paramstring[1:]))
    action = params.get('action')

    if action == 'search_menu':
        search_menu()
    elif action == 'new_search':
        new_search()
    elif action == 'search':
        search_and_show(_client(), params.get('query', ''))
    elif action == 'catalog':
        list_catalog(_client(), _catalog_url(params.get('url', 'latest')),
                     params.get('title', 'Catalog'))
    elif action == 'clear_history':
        clear_search_history()
        notify('Search history cleared.')
    elif action == 'play':
        client = _client()
        try:
            client.login()
        except AuthError as exc:
            from resources.lib.kodi_utils import show_blocking
            show_blocking('Tracker login failed: {}'.format(exc))
            return
        play_torrent(client, params.get('id', ''),
                     params.get('title', ''),
                     file_index=params.get('file_index'))
    elif action == 'files':
        list_files(_client(), params.get('id', ''),
                   params.get('title', ''))
    else:
        main_menu()


if __name__ == '__main__':
    router(sys.argv[2] if len(sys.argv) > 2 else '')
