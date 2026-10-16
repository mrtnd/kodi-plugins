# -*- coding: utf-8 -*-
"""Playback: fail-closed VPN gate, then the Elementum hand-off.

The hand-off lines are intentionally identical to the working reference
add-on - every earlier divergence in this repo cost playback in the field.
"""
from __future__ import annotations

import os
import sys
import urllib.parse

import xbmcgui
import xbmcplugin
import xbmcvfs

from resources.lib import kodi_utils as ku
from resources.lib import tracker

__profile__ = ku.profile_dir()


def vpn_check():
    """Fail-closed country gate. Returns True when playback may continue."""
    try:
        from resources.lib.vpngate import VPNGate
        country = ku.get_setting(ku.S_VPN_COUNTRY, 'BG') or 'BG'
        ok, label = VPNGate(country=country).check()
    except Exception as exc:
        ku.set_setting(ku.S_LAST_ERROR, 'VPN check error: ' + str(exc))
        return False
    if not ok:
        ku.show_error('VPN check failed (country: %s). Connect the VPN to %s '
                      'and try again.' % (label, country))
        return False
    return True


def play(torrent_url, title=''):
    if not vpn_check():
        return

    torrent_data = tracker.fetch_torrent(torrent_url)

    if not torrent_data.startswith(b'd'):
        ku.log('download did not return a torrent, first bytes: %r'
               % torrent_data[:40])
        ku.show_error('The tracker did not return a .torrent file.')
        return

    if not xbmcvfs.exists(__profile__):
        xbmcvfs.mkdirs(__profile__)

    torrent_path = os.path.join(__profile__, "elementum_temp.torrent")

    f = xbmcvfs.File(torrent_path, 'wb')
    f.write(torrent_data)
    f.close()

    uri = urllib.parse.quote_plus(torrent_path)

    elementum_url = f'plugin://plugin.video.elementum/play?uri={uri}'

    ku.log('resolved %s (%d bytes) for %s' % (elementum_url,
                                              len(torrent_data), title))
    ku.set_setting(ku.S_LAST_PLAY, elementum_url)
    ku.set_setting(ku.S_LAST_ERROR, '')

    li = xbmcgui.ListItem(path=elementum_url)
    li.setProperty('IsPlayable', 'true')

    li.setInfo('video', {'title': title})
    try:
        xbmcplugin.setResolvedUrl(int(sys.argv[1]), True, li)
    except Exception:
        ku.log('setResolvedUrl raised')
        ku.set_setting(ku.S_LAST_ERROR,
                       'setResolvedUrl raised for ' + elementum_url)
        ku.notify('This video is not available on the server.')
