"""Playback: VPN gate -> details -> .torrent -> magnet -> Elementum."""
from __future__ import annotations

from urllib.parse import quote_plus

import xbmcgui
import xbmcplugin

from resources.lib import torrentfile
from resources.lib.kodi_utils import (
    HANDLE, elementum_present, get_setting, notify, show_blocking,
)
from resources.lib.p2pbg import AuthError, build_magnet, rank_items
from resources.lib.vpngate import VPNGate

ELEMENTUM_PLAY = 'plugin://plugin.video.elementum/play?uri={}&index={}'


def _gate():
    return VPNGate(country=get_setting('vpn_country') or 'BG')


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
    try:
        info_hash = torrentfile.bencode_info_hash(raw)
    except Exception:
        info_hash = details.get('info_hash') or ''
    if not info_hash:
        show_blocking('Could not determine the torrent info-hash.')
        return
    magnet, _ = build_magnet(info_hash,
                             entries[index][0].split('/')[-1] or title,
                             torrentfile.announce_url(meta), index)
    item = xbmcgui.ListItem(path=ELEMENTUM_PLAY.format(
        quote_plus(magnet), index))
    xbmcplugin.setResolvedUrl(HANDLE, True, item)


def search_and_show(client, query):
    from resources.lib.kodi_utils import add_dir_item, end_directory
    try:
        items = client.search(
            query,
            bgaudio=get_setting('prefer_bgaudio') == 'true')
    except AuthError as exc:
        show_blocking('Tracker login failed: {}'.format(exc))
        return
    except Exception as exc:
        show_blocking('Search failed: {}'.format(exc))
        return
    items = rank_items(items,
                       min_seeders=int(get_setting('min_seeders') or 1))
    if not items:
        notify('No results (or all filtered by seeders).')
    for item in items[:50]:
        label = '{} [S:{} L:{} {}]'.format(
            item['title'], item['seeders'], item['leechers'],
            item['size'])
        add_dir_item(label, {'action': 'play', 'id': item['id'],
                             'title': item['title']},
                     is_folder=False, info={'title': item['title']})
    end_directory('Search: {}'.format(query))
