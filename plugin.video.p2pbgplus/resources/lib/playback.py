"""Catalog listing and Elementum playback.

Flow follows the proven reference plugin plugin.video.p2pbg 2026.09.24.01:
the details page of every torrent yields its ``download.php`` link, the file
is staged in the profile directory, and the local path is handed to Elementum.
Torrent items are flat playable entries - never folders.

Only two things are added on top of the reference behaviour: a fail-closed
VPN country gate before playback, and on-screen diagnostics.
"""
from __future__ import annotations

import os
from urllib.parse import quote

from resources.lib.kodi_utils import (
    add_play_item, end_directory, get_profile_dir, get_setting, log,
    notify, record_error, show_blocking,
)
from resources.lib.p2pbg import AuthError, rank_items
from resources.lib.vpngate import VPNGate

ELEMENTUM_PLAY = 'plugin://plugin.video.elementum/play?uri={}'
TORRENT_FILE = '{}.torrent'


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


# ---------------------------------------------------------------- listing
def show_items(items, next_page, category):
    """Flat playable rows: one click resolves the torrent in Elementum."""
    for item in items[:50]:
        badge = ''
        if item.get('bg_subs'):
            badge += ' [БГ субс]'
        if item.get('bg_audio'):
            badge += ' [БГ аудио]'
        label = '{} [S:{} L:{} {}]{}'.format(
            item['title'], item.get('seeders', 0), item.get('leechers', 0),
            item.get('size', ''), badge)
        add_play_item(
            label,
            {'action': 'play', 'id': item['id'], 'title': item['title'],
             'url': item.get('torrent_url', '')},
            info={'title': item['title'], 'plot': item.get('plot', ''),
                  'imdb': item.get('imdb', '')},
            art={'poster': item['poster'], 'thumb': item['poster']}
            if item.get('poster') else None)
    if next_page:
        from resources.lib.kodi_utils import add_dir_item
        add_dir_item('Следваща страница >>',
                     {'action': 'catalog', 'url': next_page})
    end_directory(category)


def _enrich(client, items):
    """Resolve each row's details page into a direct .torrent link + plot.

    Same one-request-per-row enrichment the reference plugin does; failures
    stay local to a row so one bad torrent cannot empty the listing.
    """
    for item in items[:50]:
        if item.get('enriched'):
            continue
        item['enriched'] = True
        try:
            details = client.details(item['id'])
        except AuthError:
            raise
        except Exception as exc:
            log('details failed for {}: {}'.format(item['id'], exc))
            continue
        item['torrent_url'] = details.get('torrent_url', '')
        item['imdb'] = details.get('imdb', '')
        item['info_hash'] = details.get('info_hash', '')
        item['plot'] = build_plot(details)


def build_plot(details):
    """Release/stream/seed metadata line + synopsis, tracker labels kept."""
    meta = details.get('meta', {}) or {}
    lines = []
    for label in ('Релийз', 'Видео поток'):
        if meta.get(label):
            lines.append('{}: {}'.format(label, meta[label]))
    facts = [meta[label] for label in ('Година', 'Дължина') if meta.get(label)]
    if facts:
        lines.append(' | '.join(facts))
    if meta.get('Жанр'):
        lines.append('Жанр: {}'.format(meta['Жанр']))
    if details.get('imdb'):
        lines.append('IMDb: {}'.format(details['imdb']))
    files = details.get('files') or []
    if files:
        lines.append('Файлове: {}'.format(len(files)))
    synopsis = meta.get('Резюме', '')
    if lines and synopsis:
        return '\n'.join(lines) + '\n\n' + synopsis
    return '\n'.join(lines) if lines else synopsis


def list_catalog(client, url, category='Catalog'):
    from resources.lib.p2pbg import parse_next_page, parse_search_rows
    try:
        html = client.fetch(url)
        items = parse_search_rows(html, client.base_url)
        next_page = parse_next_page(html, client.base_url)
    except AuthError as exc:
        record_error('catalog: {}'.format(exc))
        show_blocking('Tracker login failed: {}'.format(exc))
        return
    except Exception as exc:
        record_error('catalog: {}'.format(exc))
        show_blocking('Failed to load catalog: {}'.format(exc))
        return
    items = rank_items(items, min_seeders=_prefs()['min_seeders'])
    if not items:
        notify('No results.')
    try:
        _enrich(client, items)
    except AuthError as exc:
        show_blocking('Tracker login failed: {}'.format(exc))
        return
    except Exception as exc:
        log('enrich failed: {}'.format(exc))
    show_items(items, next_page, category)


def search_and_show(client, query):
    try:
        prefs = _prefs()
        items, next_page = client.search(
            query, bgaudio=prefs['bgaudio'], show_xxx=prefs['show_xxx'])
    except AuthError as exc:
        record_error('search: {}'.format(exc))
        show_blocking('Tracker login failed: {}'.format(exc))
        return
    except Exception as exc:
        record_error('search: {}'.format(exc))
        show_blocking('Search failed: {}'.format(exc))
        return
    items = rank_items(items, min_seeders=prefs['min_seeders'])
    if not items:
        notify('No results (or all filtered by seeders).')
    try:
        _enrich(client, items)
    except AuthError as exc:
        show_blocking('Tracker login failed: {}'.format(exc))
        return
    except Exception as exc:
        log('enrich failed: {}'.format(exc))
    show_items(items, next_page, 'Search: {}'.format(query))


# ---------------------------------------------------------------- playback
def _stage_torrent(raw, tid):
    """Write the .torrent into the profile dir; returns its path."""
    profile = get_profile_dir()
    path = os.path.join(profile, TORRENT_FILE.format(tid or 'download'))
    try:
        import xbmcvfs
        handle = xbmcvfs.File(path, 'wb')
        handle.write(raw)
        handle.close()
        return path
    except ImportError:
        pass
    except Exception as exc:
        log('xbmcvfs write failed, falling back: {}'.format(exc))
    with open(path, 'wb') as handle:
        handle.write(raw)
    return path


def _magnet(info_hash, name):
    if not info_hash:
        return ''
    return 'magnet:?xt=urn:btih:{}&dn={}'.format(info_hash, name)


def play(client, tid, title='', torrent_url=''):
    """VPN gate -> .torrent bytes -> staged file -> Elementum."""
    ok, label = _gate().check()
    if not ok:
        message = ('VPN check failed (country: {}). Connect the VPN to {} '
                   'and try again.'.format(label, get_setting('vpn_country')
                                           or 'BG'))
        record_error(message)
        show_blocking(message)
        return
    record_error('')
    info_hash = ''
    if not torrent_url:
        try:
            details = client.details(tid)
        except AuthError as exc:
            record_error('play: {}'.format(exc))
            show_blocking('Tracker login failed: {}'.format(exc))
            return
        except Exception as exc:
            record_error('play details: {}'.format(exc))
            show_blocking('Failed to load torrent details: {}'.format(exc))
            return
        torrent_url = details.get('torrent_url', '')
        info_hash = details.get('info_hash', '')
    if not torrent_url:
        message = 'No downloadable .torrent link on the details page.'
        record_error(message)
        show_blocking(message)
        return
    raw, error = client.download_torrent(torrent_url)
    if error and not info_hash:
        try:
            info_hash = client.details(tid).get('info_hash', '')
        except Exception:
            info_hash = ''
    if error:
        magnet = _magnet(info_hash, title)
        if magnet:
            log('torrent download failed ({}), using magnet'.format(error))
            _resolve(magnet, title)
            return
        record_error('play: {}'.format(error))
        show_blocking('Failed to fetch torrent file: {}'.format(error))
        return
    try:
        path = _stage_torrent(raw, tid)
    except Exception as exc:
        record_error('play staging: {}'.format(exc))
        show_blocking('Could not write the torrent file: {}'.format(exc))
        return
    log('staged {} ({} bytes) for {}'.format(path, len(raw), title))
    # Elementum expects a bare absolute path here (what the working reference
    # add-on passes); a file:// prefix makes it fail to play.
    _resolve(quote(path, safe='/'), title)


def _resolve(uri, title):
    """Hand the resolved URI to Kodi; never call endOfDirectory after this."""
    from resources.lib.kodi_utils import record_play, resolve_play
    record_play(uri)
    log('resolving {}'.format(uri))
    resolve_play(uri, title)
