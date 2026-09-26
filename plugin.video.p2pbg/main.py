"""Kodi entry point: search p2pbg torrents, gate VPN, play via Elementum."""
import sys
from urllib.parse import parse_qsl

import xbmcgui

from resources.lib.kodi_utils import (
    add_dir_item, add_search_history, clear_search_history, end_directory,
    get_search_history, get_setting, notify,
)
from resources.lib.p2pbg import AuthError, P2PBGClient
from resources.lib.playback import play_torrent, search_and_show


def _client():
    return P2PBGClient(
        base_url=get_setting('base_url') or 'https://www.p2pbg.com',
        username=get_setting('p2pbg_user'),
        password=get_setting('p2pbg_password'))


def main_menu():
    add_dir_item('Search', {'action': 'search_menu'})
    end_directory('P2PBG')


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
                     params.get('title', ''))
    else:
        main_menu()


if __name__ == '__main__':
    router(sys.argv[2] if len(sys.argv) > 2 else '')
