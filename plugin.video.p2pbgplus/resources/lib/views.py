# -*- coding: utf-8 -*-
"""Screen builders: menu, listings, search and diagnostics.

All user-facing text is English. The only Bulgarian left in the codebase is
inside parser patterns, because the tracker itself is a Bulgarian site.
"""
from __future__ import annotations

import os
import re
import sys
import urllib.parse

import xbmcgui
import xbmcplugin
import xbmcvfs

from resources.lib import kodi_utils as ku
from resources.lib import p2pbg
from resources.lib import tracker

_ADDON_PATH = xbmcvfs.translatePath(ku.ADDON.getAddonInfo('path'))


def _icon(name):
    return xbmcvfs.translatePath(os.path.join(_ADDON_PATH, 'resources', name))


ICON_SEARCH = _icon('search.png')
ICON_CLEAR = _icon('clear.png')
ICON_FOLDER = _icon('movies.png')
ICON_RESULT = _icon('search-result.png')

# Root menu -> the tracker's own "Movies" category optgroup. 4K is absent:
# playback drops 2160p releases entirely.
MENU_ITEMS = [
    ('Search', {'m': '5'}),
    ('Movies HD', {'m': '1', 'c': '68'}),
    ('TV Shows', {'m': '1', 'c': '14'}),
    ('TV Boxsets', {'m': '1', 'c': '15'}),
    ('All movies and shows', {'m': '1', 'c': p2pbg.ALL_CATEGORIES,
                              'bare': '1'}),
]

# Labels from older English menus, still resolvable for stale nodes.
STALE_LABELS = {
    'Movies SD': '67',
    'Movies VHS': '59',
    'Movies DVD': '11',
    'Movies Pack': '69',
    'Movies BG': '34',
    'TV BG': '24',
    'Cartoons': '38',
    'Movies Documentary': '7',
    'Movies GSM': '35',
}


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

def _bg_audio_enabled():
    return ku.get_bool(ku.S_PREFER_BGAUDIO, True)


def _show_xxx():
    return ku.get_bool(ku.S_SHOW_XXX, False)


def menu():
    """Root menu; 'files' keeps every entry drawn as a folder."""
    xbmcplugin.setContent(ku.HANDLE, 'files')
    ku.add_folder('Search', {'m': '5'}, ICON_SEARCH)
    for label, params in MENU_ITEMS[1:]:
        ku.add_folder(label, params, ICON_FOLDER)
    ku.add_folder('Diagnostics', {'m': '7'}, ICON_FOLDER)


def _plot(row):
    lines = []
    if row.get('release'):
        lines.append('[COLOR CC00FF00]Release: [/COLOR]' + str(row['release']))
    if row.get('video'):
        lines.append('[COLOR CC00FF00]Video: [/COLOR]' + str(row['video']))
    lines.append('[COLOR CC00FF00]Seeders: [/COLOR]%s '
                 '[COLOR CC00FF00]Leechers: [/COLOR]%s'
                 % (row.get('seeders', 0), row.get('leechers', 0)))
    lines.append('[COLOR CC00FF00]Size: [/COLOR]' + str(row.get('size', '')))
    if row.get('year'):
        lines.append('[COLOR CC00FF00]Year: [/COLOR]' + str(row['year']))
    if row.get('genre'):
        lines.append('[COLOR CC00FF00]Genre: [/COLOR]' + str(row['genre']))
    lines.append('[COLOR CC00FF00]BG subtitles: [/COLOR]'
                 + ('Yes' if row.get('bg_subs') else 'No'))
    lines.append('[COLOR CC00FF00]BG audio: [/COLOR]'
                 + ('Yes' if row.get('bg_audio') else 'No'))
    if row.get('synopsis'):
        lines.append('')
        lines.append('[COLOR CC00FF00]Synopsis: [/COLOR]'
                     + str(row['synopsis']))
    return '\n'.join(lines)


def _row_label(row):
    """Title plus a compact seeder/leecher badge, so activity is obvious."""
    return ('%s  [COLOR FF00FF00]S:%s[/COLOR] [COLOR FFFF4444]L:%s[/COLOR]'
            % (row.get('title', ''), row.get('seeders', 0),
               row.get('leechers', 0)))


def listing(name, url):
    xbmcplugin.setContent(ku.HANDLE, 'movies')
    ku.set_setting(ku.S_LAST_LISTING, url)
    ku.set_setting(ku.S_LAST_CATEGORY, name or 'Latest')

    try:
        rows, next_url = tracker.listing(url)
    except Exception as exc:
        # Kodi keeps the previous directory on screen when a plugin dies
        # before endOfDirectory, which looks like a stuck/duplicated menu.
        ku.set_setting(ku.S_LAST_ITEMS, '0')
        ku.log('listing request failed for %s: %r' % (url, exc))
        ku.show_error('Failed to load the listing.\n\n%s' % exc)
        return

    for row in rows:
        url_for_play = (sys.argv[0] + '?url='
                        + urllib.parse.quote_plus(row['torrent_url'])
                        + '&mode=2&name='
                        + urllib.parse.quote_plus(row['title']))
        ku.add_playable(_row_label(row), url_for_play,
                        row.get('image') or ICON_FOLDER, _plot(row),
                        row.get('imdb_id', ''))

    ku.set_setting(ku.S_LAST_ITEMS, str(len(rows)))

    if next_url:
        ku.add_folder('[COLOR CC00FF00][B]Next page >>[/B][/COLOR]',
                      {'m': '1', 'u': next_url, 'n': name or 'Latest'},
                      ICON_FOLDER)


def search_screen():
    xbmcplugin.setContent(ku.HANDLE, 'files')
    ku.add_folder('New search', {'m': '10'}, ICON_SEARCH)
    history = ku.load_history()
    for item in history:
        text = item.get('text', '')
        if text:
            ku.add_folder(text, {'m': '4', 'q': text}, ICON_RESULT)
    if history:
        ku.add_folder('Clear history', {'m': '6'}, ICON_CLEAR)


def clear_history():
    ku.clear_history()


def diagnostics():
    try:
        from resources.lib.vpngate import VPNGate
        country = ku.get_setting(ku.S_VPN_COUNTRY, 'BG') or 'BG'
        ok, label = VPNGate(country=country).check()
    except Exception as exc:
        ok, label = False, 'check error: ' + str(exc)
    try:
        xbmcaddon = __import__('xbmcaddon')
        xbmcaddon.Addon('plugin.video.elementum')
        elementum = 'installed'
    except Exception:
        elementum = 'NOT INSTALLED'
    lines = [
        'Elementum: ' + elementum,
        'VPN country: %s (required %s, gate %s)' % (
            label, country, 'OK' if ok else 'BLOCKED'),
        'User: ' + (ku.get_setting(ku.S_USER) or '(not set)'),
        'Profile: ' + ku.profile_dir(),
        'Last call: ' + (ku.get_setting(ku.S_LAST_CALL) or 'none'),
        'Last listing: ' + ((ku.get_setting(ku.S_LAST_CATEGORY) or '?')
                            + ' -> '
                            + (ku.get_setting(ku.S_LAST_LISTING) or 'none')),
        'Table: ' + (ku.get_setting(ku.S_LAST_TABLE) or '?')
        + ', items: ' + (ku.get_setting(ku.S_LAST_ITEMS) or '?'),
        'Last play: ' + (ku.get_setting(ku.S_LAST_PLAY) or 'none'),
        'Last error: ' + (ku.get_setting(ku.S_LAST_ERROR) or 'none'),
    ]
    xbmcgui.Dialog().ok('P2PBG+ diagnostics', '\n'.join(lines))


# --------------------------------------------------------------------------
# Search
# --------------------------------------------------------------------------

def search(query=None):
    """Run a search over all categories (category=0).

    With a query the search runs at once (history entry); without one the
    keyboard is shown first. Spaces stay plus-encoded, exactly like the
    confirmed search URL.
    """
    if query and '/torrents' in query:
        listing('Search', query)
        return
    if query:
        ku.add_to_history(query)
        listing('Search: ' + query,
                p2pbg.search_url(query, bgaudio=_bg_audio_enabled(),
                                 show_xxx=_show_xxx()))
        return
    try:
        text = xbmcgui.Dialog().input('Search')
    except Exception as exc:
        ku.log('search input failed: %r' % (exc,))
        ku.show_error('Search input is not available. Open Diagnostics for '
                      'details.')
        return
    if text and text.strip():
        search(text.strip())
    else:
        search_screen()


# --------------------------------------------------------------------------
# Routing helpers
# --------------------------------------------------------------------------

def run_compact(params, label=''):
    """Execute a compact menu request (m/c/q/u/n/bare keys)."""
    mode = params.get('m')
    if mode == '1':
        cats = params.get('c', '')
        if params.get('bare') == '1' or cats == p2pbg.ALL_CATEGORIES:
            url = p2pbg.all_url()
        else:
            url = p2pbg.listing_url(cats, bgaudio=_bg_audio_enabled(),
                                    show_xxx=_show_xxx())
        listing(label or 'Category', url)
    elif mode == '4':
        search(params.get('q', ''))
    elif mode == '5':
        search_screen()
    elif mode == '10':
        search()
    elif mode == '6':
        clear_history()
    elif mode == '7':
        diagnostics()
    elif mode == '9':
        menu()
    else:
        ku.show_error('Cannot open "%s". Try it again from the menu.'
                      % (label or 'this item'))


def resolve_label(label):
    """Best-effort action for a menu click that lost its parameters.

    The label survives even when the request query did not, and together
    with the settings it is everything the request needs.
    Returns True when something was rendered.
    """
    if not label:
        return False
    label = label.strip().rstrip('/')
    if label == 'Menu':
        menu()
        return True
    if label == 'Diagnostics':
        diagnostics()
        return True
    if label == 'Search':
        search_screen()
        return True
    for menu_label, params in MENU_ITEMS[1:]:
        if menu_label == label:
            run_compact(params, label)
            return True
    if label in STALE_LABELS:
        run_compact({'m': '1', 'c': STALE_LABELS[label]}, label)
        return True
    year = re.fullmatch(r'Movies from (\d{4})', label)
    if year:
        run_compact({'m': '4', 'q': year.group(1)}, label)
        return True
    # The label may be cut off mid-word, so accept a unique prefix match
    # ('TV Shows' must not also match nothing else - the exact pass is above).
    if len(label) >= 3:
        known = [menu_label for menu_label, _ in MENU_ITEMS[1:]]
        candidates = [menu_label for menu_label in known
                      if menu_label.startswith(label)
                      or label.startswith(menu_label)]
        if len(candidates) == 1:
            return resolve_label(candidates[0])
    return False
