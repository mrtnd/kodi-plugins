# -*- coding: utf-8 -*-
"""Playback hand-off: resolveurl, subtitles, ``setResolvedUrl``.

This is the fork's fidelity surface. The reference add-on's play path
(plugin.video.filmifen 2026.05.05.01) is the only version confirmed to
play with script.module.findstreamurl on the target devices, so the
resolver call and the ``setResolvedUrl`` hand-off are kept verbatim.
Do not "improve" them: the tests pin the exact lines.
"""
from __future__ import annotations

import sys
import urllib.request

import xbmc
import xbmcgui
import xbmcplugin

from resources.lib import kodi_utils as ku

try:
    import resolveurl
except ImportError:  # dependency not installed; reported on first play
    resolveurl = None


def play(url, name='', iconimage=''):
    """Resolve one stream URL and hand it to Kodi (reference logic)."""
    if resolveurl is None:
        ku.show_error('Resolver missing: install script.module.findstreamurl.')
        return

    newurl = url

    link_sub = resolveurl.resolve(newurl)
    link = link_sub[0]
    suburl = link_sub[1]

    if link != '':
        li = xbmcgui.ListItem(path=link)

        # Subtitles, exactly like the reference add-on (its UA header and
        # temp file name are kept byte-for-byte).
        if suburl != '':
            subfile = ku.SUBTITLE_FILE
            open(subfile, 'w').close()
            opener = urllib.request.build_opener()
            opener.addheaders = [('User-Agent', 'UA')]
            urllib.request.install_opener(opener)
            urllib.request.urlretrieve(suburl, subfile)
            li.setSubtitles([subfile])
            xbmc.executebuiltin(
                'Notification(%s, %s, %d, %s)'
                % (ku.ADDON_NAME, 'Loading subtitles...', 3000,
                   'DefaultAddonSubtitles.png'))

        if iconimage:
            li.setArt({'thumb': iconimage, 'poster': iconimage,
                       'banner': iconimage, 'fanart': iconimage})
        li.setInfo('video', {'title': name})
        try:
            xbmcplugin.setResolvedUrl(int(sys.argv[1]), True, li)
        except Exception:
            xbmc.executebuiltin("Notification('Error','Missing video!')")
    else:
        xbmc.executebuiltin("Notification('Error','Missing video!')")
