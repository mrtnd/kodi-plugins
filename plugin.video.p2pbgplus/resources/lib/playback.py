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


def _min_seeders():
    try:
        return max(0, int((get_setting('min_seeders') or '1').strip()))
    except (TypeError, ValueError):
        return 1


def _prefs():
    return {
        'bgaudio': get_setting('prefer_bgaudio') == 'true',
        'show_xxx': get_setting('show_xxx') == 'true',
        'min_seeders': _min_seeders(),
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
        add_dir_item(label, {'action': 'files', 'id': item['id'],
                             'title': item['title']},
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


def _fetch_torrent(client, tid, title=''):
    """Details + .torrent bytes + decoded meta, with user-facing errors.

    Prefers the direct download.php?id=<tid> path (same id as the details
    page); falls back to scraping the details page for the download link.
    """
    raw = None
    try:
        raw = client.download_by_id(tid, title or tid)
    except AuthError as exc:
        return None, 'Tracker login failed: {}'.format(exc)
    except Exception:
        raw = None
    if raw is None:
        try:
            details = client.details(tid)
        except AuthError as exc:
            return None, 'Tracker login failed: {}'.format(exc)
        except Exception as exc:
            return None, 'Failed to load torrent details: {}'.format(exc)
        if not details.get('torrent_url'):
            return None, 'No downloadable torrent file on the details page.'
        try:
            raw = client.download_torrent(details['torrent_url'])
        except Exception as exc:
            return None, 'Failed to fetch torrent file: {}'.format(exc)
    try:
        meta = torrentfile.bdecode(raw)
    except Exception as exc:
        return None, 'Failed to parse torrent file: {}'.format(exc)
    return (raw, meta), ''


def list_files(client, tid, title=''):
    """Episode/file picker. Single-video torrents play immediately."""
    from resources.lib.kodi_utils import add_dir_item, end_directory
    result, error = _fetch_torrent(client, tid, title)
    if error:
        show_blocking(error)
        return
    _raw, meta = result
    videos = torrentfile.video_files(torrentfile.file_entries(meta))
    if not videos:
        show_blocking('No video file inside this torrent.')
        return
    if len(videos) == 1:
        play_torrent(client, tid, title, file_index=videos[0][0])
        return
    try:
        summary = client.preview(tid)
    except Exception:
        summary = {}
    plot = summary.get('plot', '')
    for index, path, _size in videos:
        name = path.split('/')[-1]
        art = None
        if summary.get('poster'):
            art = {'poster': summary['poster'],
                   'thumb': summary['poster'],
                   'fanart': summary['poster']}
        add_dir_item(name, {'action': 'play', 'id': tid,
                            'title': name, 'file_index': str(index)},
                     is_folder=False,
                     info={'title': name, 'plot': plot} if plot
                     else {'title': name},
                     art=art)
    end_directory(title or 'Select file')


def play_torrent(client, tid, title='', file_index=None):
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
    result, error = _fetch_torrent(client, tid, title)
    if error:
        show_blocking(error)
        return
    raw, meta = result
    videos = torrentfile.video_files(torrentfile.file_entries(meta))
    if not videos:
        show_blocking('No video file inside this torrent.')
        return
    try:
        wanted = int(file_index) if file_index is not None else None
    except (TypeError, ValueError):
        wanted = None
    index = wanted if wanted in [v[0] for v in videos] else videos[0][0]
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
