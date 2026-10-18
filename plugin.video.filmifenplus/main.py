# -*- coding: utf-8 -*-
"""FilmiFen+ Kodi add-on entry point.

Fork of plugin.video.filmifen 2026.05.05.01 (GPL-3.0, MartinStZ). The
parser lives in resources/lib/filmifen.py, the Kodi adapters in
kodi_utils.py, the screens in views.py and the resolver hand-off in
playback.py.
"""
from __future__ import annotations

import sys
import urllib.parse

from resources.lib import kodi_utils as ku
from resources.lib import playback
from resources.lib import views


def get_params(paramstring):
    """Parse the plugin query with parse_qsl.

    Unlike the reference add-on's manual split, a trailing slash, a blank
    value or a stray ``?`` cannot drop mode/url and land the user back in
    the root menu.
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


def router(paramstring):
    params = get_params(paramstring)

    url = _unquote(params.get('url'))
    name = _unquote(params.get('name'))
    plot = _unquote(params.get('plot'))
    iconimage = _unquote(params.get('iconimage'))
    mode = _int(params.get('mode'))

    is_root = not paramstring or len(paramstring) < 2
    ku.log('call mode=%s url=%s' % (mode, (url or '')[:200]))

    try:
        if mode is None and is_root:
            # The root menu is rendered only at the add-on root, never as a
            # side effect of a click that could not be resolved (that made
            # every selection re-render the menu as a nested folder in the
            # reference add-on).
            views.menu()

        elif mode == ku.MODE_LISTING:
            if url:
                views.listing(url)
            else:
                ku.show_error('Cannot open "%s": request has no URL.'
                              % (name or 'this item'))

        elif mode == ku.MODE_SEARCH:
            views.search()

        elif mode == ku.MODE_STREAMS:
            if url:
                views.streams(name or '', url, plot or '', iconimage or '')
            else:
                ku.show_error('Cannot open "%s": request has no URL.'
                              % (name or 'this item'))

        elif mode == ku.MODE_PLAY:
            if url:
                playback.play(url, name or '', iconimage or '')
            else:
                ku.show_error('Cannot play "%s": request has no URL.'
                              % (name or 'this item'))

        else:
            ku.show_error('Cannot open "%s". Try it again from the menu.'
                          '\n\nRequest: %s'
                          % (name or 'this item', paramstring[:300]))

    except Exception as exc:
        import traceback
        ku.log('dispatch failed: %r\n%s' % (exc, traceback.format_exc()))
        ku.show_error('Error: %s\n\nRequest: %s'
                      % (exc, paramstring[:300]))

    finally:
        # Live listings must never be served from Kodi's directory cache.
        ku.end_directory(cache_to_disc=False)


if __name__ == '__main__':
    router(sys.argv[2] if len(sys.argv) > 2 else '')
