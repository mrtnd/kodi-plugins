"""Playback: VPN gate -> details -> .torrent file -> Elementum.

Mirrors the proven reference flow (download .torrent via the tracker
session, stage it in the profile dir, hand the local path to Elementum),
plus a fail-closed VPN country gate and largest-video auto-selection.
"""
from __future__ import annotations

import os
from urllib.parse import quote_plus

import xbmcgui
import xbmcplugin

from resources.lib import torrentfile
from resources.lib.kodi_utils import (
    HANDLE, elementum_present, get_profile_dir, get_setting, notify,
    show_blocking,
)
from resources.lib.p2pbg import AuthError, rank_items
from resources.lib.vpngate import VPNGate

ELEMENTUM_PLAY = 'plugin://plugin.video.elementum/play?uri={}&index={}'


def _gate():
    return VPNGate(country=get_setting('vpn_country') or 'BG')


def _prefs():
    return {
        'bgaudio': get_setting('prefer_bgaudio') == 'true',
        'show_xxx': get_setting('show_xxx') == 'true',
        'min_seeders': int(get_setting('min_seeders') or 1),
    }


def show_items(items, next_page, category):
    from resources.lib.kodi_utils import add_dir_item, end_directory
    for item in items[:50]:
        badge = ''
        if item.get('bg_subs'):
            badge += ' [БГ субс]'
        if item.get('bg_audio'):
            badge += ' [БГ аудио]'
        label = '{} [S:{} L:{} {}]{}'.format(
            item['title'], item['seeders'], item['leechers'],
            item['size'], badge)
        art = {'poster': item['poster'],
               'thumb': item['poster']} if item.get('poster') else None
        add_dir_item(label, {'action': 'play', 'id': item['id'],
                             'title': item['title']},
                     is_folder=False,
                     info={'title': item['title']}, art=art)
    if next_page:
        add_dir_item('Следваща страница >>',
                     {'action': 'catalog', 'url': next_page})
    end_directory(category)


def list_catalog(client, url, category='Catalog'):
    from resources.lib.p2pbg import parse_next_page, parse_search_rows
    try:
        html = client.fetch(url)
        items = parse_search_rows(html, client.base_url)
        next_page = parse_next_page(html, client.base_url)
    except AuthError as exc:
        show_blocking('Tracker login failed: {}'.format(exc))
        return
    except Exception as exc:
        show_blocking('Failed to load catalog: {}'.format(exc))
        return
    items = rank_items(items, min_seeders=_prefs()['min_seeders'])
    if not items:
        notify('No results.')
    show_items(items, next_page, category)


def search_and_show(client, query):
    try:
        prefs = _prefs()
        items, next_page = client.search(
            query, bgaudio=prefs['bgaudio'], show_xxx=prefs['show_xxx'])
    except AuthError as exc:
        show_blocking('Tracker login failed: {}'.format(exc))
        return
    except Exception as exc:
        show_blocking('Search failed: {}'.format(exc))
        return
    items = rank_items(items, min_seeders=prefs['min_seeders'])
    if not items:
        notify('No results (or all filtered by seeders).')
    show_items(items, next_page, 'Search: {}'.format(query))


def play_torrent(client, tid, title=''):
    if not elementum_present():
        notify('Install the Elementum add-on first (torrent engine).')
        return
    gate = _gate()
    ok, label = gate.check()
    if not ok:
        show_blocking(
            'VPN country check failed (got: {}).\n'
            'Connect the VPN to {} and retry. Playback is blocked '
            'while the check does not pass.'.format(label or '?',
                                                    gate.country))
        return
    try:
        details = client.details(tid)
    except AuthError as exc:
        show_blocking('Tracker login failed: {}'.format(exc))
        return
    except Exception as exc:
        show_blocking('Failed to load torrent details: {}'.format(exc))
        return
    if not details.get('torrent_url'):
        show_blocking('No downloadable torrent file on the details page.')
        return
    try:
        raw = client.download_torrent(details['torrent_url'])
        meta = torrentfile.bdecode(raw)
    except Exception as exc:
        show_blocking('Failed to fetch torrent file: {}'.format(exc))
        return
    entries = torrentfile.file_entries(meta)
    index = torrentfile.largest_video_index(entries)
    if index is None:
        show_blocking('No video file inside this torrent.')
        return
    path = os.path.join(get_profile_dir(), 'elementum_temp.torrent')
    try:
        with open(path, 'wb') as handle:
            handle.write(raw)
    except Exception as exc:
        show_blocking('Failed to stage torrent file: {}'.format(exc))
        return
    item = xbmcgui.ListItem(
        path=ELEMENTUM_PLAY.format(quote_plus(path), index))
    xbmcplugin.setResolvedUrl(HANDLE, True, item)
