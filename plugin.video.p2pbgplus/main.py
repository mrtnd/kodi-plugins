"""Kodi entry point: categories, search, catalog, VPN-gated Elementum play."""
import sys
from urllib.parse import parse_qsl

import xbmcgui

from resources.lib.kodi_utils import (
    add_dir_item, add_search_history, clear_search_history, end_directory,
    get_last_error, get_search_history, get_setting, notify, show_blocking,
)
from resources.lib.p2pbg import CATEGORIES, DEFAULT_CATEGORIES, P2PBGClient
from resources.lib.playback import list_catalog, play, search_and_show


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
                                       'url': 'cat:'})
    for offset in range(3):
        add_dir_item('Филми от {} година'.format(year - offset),
                     {'action': 'search', 'query': str(year - offset)})
    for cat_id, cat_name in CATEGORIES:
        add_dir_item(cat_name, {'action': 'catalog',
                                'url': 'cat:' + cat_id})
    add_dir_item('Диагностика', {'action': 'diagnostics'})
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
    """Latest / category listing URL; next-page URLs pass through untouched."""
    if not spec.startswith('cat:'):
        return spec  # next-page absolute URL
    client = _client()
    prefs = _prefs()
    categories = spec[4:] if spec[4:] else DEFAULT_CATEGORIES
    return client.listing_url(categories=categories, bgaudio=prefs['bgaudio'],
                              show_xxx=prefs['show_xxx'])


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


def diagnostics():
    """On-screen state so a failure can be read on the TV, not guessed."""
    from resources.lib.kodi_utils import (
        elementum_present, get_last_play, get_profile_dir)
    from resources.lib.vpngate import VPNGate
    user = get_setting('p2pbg_user') or '(not set)'
    ok, label = VPNGate(country=get_setting('vpn_country') or 'BG').check()
    lines = [
        'Elementum: {}'.format('installed' if elementum_present()
                                else 'NOT INSTALLED'),
        'VPN country: {} (required {}, gate {})'.format(
            label, get_setting('vpn_country') or 'BG', 'OK' if ok else 'BLOCKED'),
        'User: {}'.format(user),
        'Profile: {}'.format(get_profile_dir()),
        'Last play: {}'.format(get_last_play() or 'none'),
        'Last error: {}'.format(get_last_error() or 'none'),
    ]
    show_blocking('\n'.join(lines), title='P2PBG+ diagnostics')


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
        play(_client(), params.get('id', ''), params.get('title', ''),
             params.get('url', ''))
    elif action == 'diagnostics':
        diagnostics()
    elif action == 'files':
        # Stale bookmarks from the folder-based picker: play instead.
        play(_client(), params.get('id', ''), params.get('title', ''))
    else:
        main_menu()


if __name__ == '__main__':
    router(sys.argv[2] if len(sys.argv) > 2 else '')
