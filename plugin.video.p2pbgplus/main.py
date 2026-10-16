# -*- coding: utf-8 -*-
"""P2PBG+ Kodi add-on entry point.

Fork of plugin.video.p2pbg 2026.09.24.01 (GPL-3.0, MartinStZ). The tracker
logic lives in resources/lib/p2pbg.py, the Kodi adapters in kodi_utils.py,
the screens in views.py and the Elementum hand-off in playback.py.
"""
from __future__ import annotations

import sys
import urllib.parse

from resources.lib import kodi_utils as ku
from resources.lib import p2pbg
from resources.lib import playback
from resources.lib import views

COMPACT_KEYS = ('m', 'c', 'q', 'u', 'n', 'bare')


def get_params(paramstring):
    """Parse the plugin query with parse_qsl.

    A trailing slash, a blank value such as search= or any stray character
    cannot drop mode/url and land the user back in the root menu.
    """
    if not paramstring or len(paramstring) < 2:
        return {}
    return dict(urllib.parse.parse_qsl(paramstring.lstrip('?'),
                                       keep_blank_values=True))


def _unquote(value):
    if value is None:
        return None
    try:
        return urllib.parse.unquote_plus(value)
    except Exception:
        return value


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _bootstrap():
    if ku.get_setting(ku.S_FIRSTRUN) == 'true':
        ku.notify('Open settings and enter your p2pbg.com credentials.')
        try:
            ku.ADDON.openSettings()
        except Exception:
            pass
        ku.set_setting(ku.S_FIRSTRUN, 'false')
    if not ku.get_setting(ku.S_USER):
        ku.notify('p2pbg username is not set.')
    if not ku.get_setting(ku.S_PASSWORD):
        ku.notify('p2pbg password is not set.')


def router(paramstring):
    params = get_params(paramstring)

    url = _unquote(params.get('url'))
    name = _unquote(params.get('name'))
    mode = _int(params.get('mode'))
    compact = {key: params.get(key) for key in COMPACT_KEYS
               if params.get(key) not in (None, '')}
    if not name:
        name = compact.get('n') or None

    is_root = not paramstring or len(paramstring) < 2
    recovered = p2pbg.recover_listing_url(paramstring)
    label = name or compact.get('n') or ''

    # What did Kodi actually hand us? Shown by Diagnostics, because a mangled
    # query is the difference between a listing and the root menu reappearing.
    ku.set_setting(ku.S_LAST_CALL, 'mode=%s url=%s raw=%s' % (
        compact.get('m', mode), (compact.get('u') or url or '')[:200],
        paramstring[:400]))

    try:
        if compact.get('m') == '1' and compact.get('u'):
            # Next-page link: the only compact request carrying a full URL.
            views.listing(label or 'Category', compact['u'])

        elif compact.get('m') in ('1', '4', '5', '6', '7', '9', '10'):
            views.run_compact(compact, label)

        elif compact:
            ku.log('unknown compact request: raw=%s' % paramstring)
            ku.show_error('Cannot open this item. Try it again from the '
                          'menu.\n\nRequest: %s' % paramstring[:300])

        elif mode is None and is_root:
            # The add-on root always shows the menu. Reopening the last
            # listing here stranded users on it with no way back to browse.
            views.menu()

        elif mode is None:
            if name and views.resolve_label(name):
                pass
            elif (url or recovered) and '/torrents' in (url or recovered):
                views.listing(label or ku.get_setting(ku.S_LAST_CATEGORY,
                                                      'Latest'),
                              url or recovered)
            else:
                # Report with the request attached; showing other content here
                # is what made every category display previous results.
                ku.log('unresolvable call: raw=%s' % paramstring)
                ku.show_error('Cannot open "%s". Try it again from the menu.'
                              '\n\nRequest: %s'
                              % (label or 'this item', paramstring[:300]))

        elif mode == 9:
            # Stale "Menu" entry: the menu is only ever rendered on request.
            views.menu()

        elif mode == 7:
            views.diagnostics()

        elif mode == 6:
            views.clear_history()

        elif mode == 2:
            playback.play(url, name or '')

        elif mode == 5:
            views.search_screen()

        elif mode in (1, 4):
            address = url or recovered
            if not address and name and views.resolve_label(name):
                pass
            elif not address:
                ku.log('unresolvable call: mode=%s name=%s raw=%s'
                       % (mode, name, paramstring))
                ku.show_error('Cannot open "%s". Try it again from the menu.'
                              '\n\nRequest: %s'
                              % (name or 'this item', paramstring[:300]))
            elif mode == 4:
                views.search(address)
            else:
                views.listing(name, address)

        else:
            ku.log('unresolvable call: mode=%s url=%s raw=%s'
                   % (mode, url, paramstring))
            ku.show_error('Cannot open "%s". Try it again from the menu.'
                          '\n\nRequest: %s'
                          % (name or 'this item', paramstring[:300]))

    except Exception as exc:
        import traceback
        ku.log('dispatch failed: %r\n%s' % (exc, traceback.format_exc()))
        ku.show_error('Error: %s\n\nRequest: %s'
                      % (exc, paramstring[:300]))

    finally:
        # cacheToDisc=False: Kodi must never serve a saved copy of a live
        # tracker listing, otherwise a revisited category shows old content.
        ku.end_directory(cache_to_disc=False)


if __name__ == '__main__':
    _bootstrap()
    router(sys.argv[2] if len(sys.argv) > 2 else '')
